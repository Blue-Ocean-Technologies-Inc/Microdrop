"""Runtime hot load/unload of *named groups* of Envisage plugins.

Groups come from the declarative BUILTIN_PLUGIN_GROUPS registry (consts.py);
plugin classes are dotted "module:Class" specs resolved lazily at enable/adopt
time, so a broken plugin never breaks startup.

Envisage supports adding/removing plugins at runtime, but two layers don't
self-heal: runtime ServiceOffers leak (CorePlugin discards their ids), and a
plugin's resources outlive a bare stop(). This orchestrator captures runtime
service ids generically and relies on each plugin's own stop()/teardown for
the rest. Dock panes + the menu bar are mounted/unmounted **reactively** by
LiveTaskExtensionsController when TASK_EXTENSIONS change, and topic routing by
the message router when ACTOR_TOPIC_ROUTES change — this manager never touches
the view layer.

Startup-loaded groups (the built-ins are also registered in plugin_consts.py)
are ADOPTED at launch: their live instances are attached to the group so a
toggle-off manages exactly what this process loaded. ``active_specs`` remembers
which halves of a group live in THIS process (frontend-only / backend-only
runs), so a later re-enable brings back only those.
"""
import importlib

from traits.api import Bool, Dict, HasTraits, Instance, List, Str, provides

from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from .consts import BUILTIN_PLUGIN_GROUPS
from .i_plugin_group_manager import IPluginGroupManager

logger = get_logger(__name__)

app_globals = get_microdrop_redis_globals_manager()


def _resolve_plugin_class(spec):
    """Import a "module:Class" spec to the plugin class."""
    module_path, _, class_name = spec.partition(":")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class PluginGroup(HasTraits):
    """One named, ordered set of plugins that load/unload together."""

    name = Str()
    #: User-visible label (shown in the Manage Plugins dialog).
    label = Str()
    #: Plugin classes as dotted "module:Class" specs, in load order (unloaded
    #: in reverse). Resolved to classes lazily at enable/adopt time.
    plugin_specs = List(Str)
    #: The subset of plugin_specs active in THIS process — set by adoption
    #: (startup composition) or the last enable. A frontend-only process
    #: adopts just the UI half, and re-enabling brings back only that half.
    active_specs = List(Str)
    #: Live plugin instances while loaded (empty otherwise).
    instances = List()
    #: Service-registry ids registered while the group loaded, captured by a
    #: before/after snapshot so disable() can unregister exactly them.
    #: Empty for adopted groups (their services registered at startup and are
    #: cleaned up by each plugin's own stop()).
    service_ids = List()
    loaded = Bool(False)
    #: App-globals flag persisting this group's enabled state across runs.
    enabled_key = Str()
    #: Optional topic published (empty message) right after a successful
    #: enable — re-kicks the device's connection search, since the plugin's
    #: own application_initialized probe never fires on a hot enable.
    post_enable_publish_topic = Str()


@provides(IPluginGroupManager)
class PluginGroupManager(HasTraits):
    """Discovers, loads, and unloads named plugin groups against a live
    application. Offered as an Envisage service by PluginManagementPlugin;
    the Manage Plugins dialog and the launch-restore hook use it."""

    groups = Dict(Str, Instance(PluginGroup))

    def _groups_default(self):
        return {
            spec["name"]: PluginGroup(**spec) for spec in BUILTIN_PLUGIN_GROUPS
        }

    # --- launch integration -------------------------------------------

    def adopt_running(self, application):
        """Attach already-registered plugin instances (startup composition) to
        their groups so a toggle-off manages them. Marks a group loaded when at
        least one of its plugins is present in this process."""
        for group in self.groups.values():
            if group.loaded:
                continue
            instances, active = [], []
            for spec in group.plugin_specs:
                try:
                    plugin_id = getattr(_resolve_plugin_class(spec), "id", None)
                except Exception as e:
                    logger.warning(f"adopt: cannot resolve {spec!r}: {e}")
                    continue
                plugin = (application.get_plugin(plugin_id)
                          if plugin_id else None)
                if plugin is not None:
                    instances.append(plugin)
                    active.append(spec)
            if instances:
                group.instances = instances
                group.active_specs = active
                group.loaded = True
                logger.info(
                    f"adopt: group '{group.name}' loaded from startup "
                    f"({len(instances)}/{len(group.plugin_specs)} plugins in "
                    f"this process)")

    def restore_persisted(self, application):
        """Reconcile every group to its persisted enabled flag (default:
        enabled, so out of the box nothing changes). Runs after adoption, so a
        persisted 'off' unloads the startup-composed group."""
        desired = {}
        for name, group in self.groups.items():
            enabled = True
            if group.enabled_key:
                try:
                    enabled = bool(app_globals.get(group.enabled_key, True))
                except Exception as e:   # tolerated no-Redis path
                    logger.debug(f"restore: no app_globals for {name}: {e}")
            desired[name] = enabled
        self.apply(application, desired)

    # --- public API ----------------------------------------------------

    def is_loaded(self, group_name):
        group = self.groups.get(group_name)
        return bool(group is not None and group.loaded)

    def apply(self, application, desired):
        """Reconcile group load state to ``desired`` ({group_name: bool}).
        Enables newly-on groups in registration order; disables newly-off
        groups in reverse. Only groups whose desired state differs are
        touched."""
        names = list(self.groups.keys())
        for group_name in names:
            if desired.get(group_name) and not self.is_loaded(group_name):
                self.enable(application, group_name)
        for group_name in reversed(names):
            if (group_name in desired
                    and not desired[group_name]
                    and self.is_loaded(group_name)):
                self.disable(application, group_name)

    def enable(self, application, group_name):
        """Resolve the group's plugin specs, add + start them, capture the
        services they register, and run the optional post-enable publish.
        Idempotent — a no-op if the group is already loaded.

        Dock panes + the menu bar are mounted/rebuilt reactively by
        LiveTaskExtensionsController when these plugins contribute their
        TASK_EXTENSIONS — this method never touches the view layer."""
        group = self.groups.get(group_name)
        if group is None:
            logger.warning(f"enable: unknown plugin group '{group_name}'")
            return
        if group.loaded:
            logger.info(f"enable: group '{group_name}' already loaded")
            return

        # Prefer the specs that were active in this process before (adoption /
        # last enable); fall back to the full list on first-ever enable.
        specs = group.active_specs or group.plugin_specs
        try:
            factories = [_resolve_plugin_class(spec) for spec in specs]
        except Exception:
            logger.exception(
                f"enable: could not import plugin classes for '{group_name}'; "
                f"group not loaded")
            return

        registry = application.service_registry
        before = set(registry._services.keys())

        for factory in factories:
            try:
                plugin = factory()
                application.add_plugin(plugin)
                application.start_plugin(plugin)
                group.instances.append(plugin)
                logger.info(f"enable: started {plugin.id}")
            except Exception:
                logger.exception(
                    f"enable: failed to load "
                    f"{getattr(factory, '__name__', factory)}")

        group.active_specs = list(specs)
        group.service_ids = sorted(set(registry._services.keys()) - before)
        logger.info(f"enable: captured service ids {group.service_ids}")

        if group.post_enable_publish_topic:
            try:
                publish_message(topic=group.post_enable_publish_topic, message="")
                logger.info(f"enable: published {group.post_enable_publish_topic}")
            except Exception:
                logger.exception(
                    f"enable: failed to publish {group.post_enable_publish_topic}")

        group.loaded = True
        self._persist_flag(group, True)
        logger.info(f"enable: group '{group_name}' loaded")

    def disable(self, application, group_name):
        """Reverse of enable: stop + remove every plugin (reverse order) and
        unregister the captured services. Idempotent — a no-op if the group
        isn't loaded. The contributed dock panes are unmounted and the menu
        bar rebuilt reactively when remove_plugin withdraws TASK_EXTENSIONS."""
        group = self.groups.get(group_name)
        if group is None:
            logger.warning(f"disable: unknown plugin group '{group_name}'")
            return
        if not group.loaded:
            logger.info(f"disable: group '{group_name}' not loaded")
            return

        for plugin in reversed(group.instances):
            pid = getattr(plugin, "id", plugin)
            try:
                application.stop_plugin(plugin)
            except Exception:
                logger.exception(f"disable: stop_plugin failed for {pid}")
            try:
                application.remove_plugin(plugin)
            except Exception:
                logger.exception(f"disable: remove_plugin failed for {pid}")
            logger.info(f"disable: removed {pid}")
        group.instances = []

        for service_id in group.service_ids:
            try:
                application.unregister_service(service_id)
                logger.info(f"disable: unregistered service id {service_id}")
            except Exception:
                logger.exception(
                    f"disable: unregister_service failed for {service_id}")
        group.service_ids = []

        group.loaded = False
        self._persist_flag(group, False)
        logger.info(f"disable: group '{group_name}' unloaded")

    # --- helpers -------------------------------------------------------

    @staticmethod
    def _persist_flag(group, value):
        if not group.enabled_key:
            return
        try:
            app_globals[group.enabled_key] = value
        except Exception as e:           # tolerated no-Redis path
            logger.debug(f"could not persist {group.enabled_key}: {e}")

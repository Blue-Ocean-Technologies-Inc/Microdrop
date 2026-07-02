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

from . import entry_point_discovery
from .consts import BUILTIN_PLUGIN_GROUPS
from .i_plugin_group_manager import IPluginGroupManager

logger = get_logger(__name__)

app_globals = get_microdrop_redis_globals_manager()


def _resolve_plugin_class(spec):
    """Import a "module:Class" spec to the plugin class."""
    module_path, _, class_name = spec.partition(":")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _find_registered_plugin(application, plugin_class):
    """The already-registered plugin INSTANCE of ``plugin_class``, or None.

    Matched by isinstance against the live plugin manager — a Plugin's ``id``
    cannot be read off the CLASS (Traits swallows the class-level default), so
    id-based lookup silently returns None and breaks adoption."""
    try:
        for plugin in application.plugin_manager:
            if isinstance(plugin, plugin_class):
                return plugin
    except Exception as e:
        logger.debug(f"plugin-manager scan failed: {e}")
    return None


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
    #: The owning manifest's name + label, and the distribution the manifest
    #: was shipped by. Empty for built-in groups; used to classify bundled vs.
    #: installed plugins (installed_plugins / uninstall).
    manifest_name = Str()
    manifest_label = Str()
    dist_name = Str()
    #: Owning manifest's version (shown next to the plugin name).
    manifest_version = Str()
    #: True if this group is independently toggleable; built-ins always are.
    optional = Bool(True)
    #: Short label for the toggle checkbox column (falls back to label).
    toggle_label = Str()


@provides(IPluginGroupManager)
class PluginGroupManager(HasTraits):
    """Discovers, loads, and unloads named plugin groups against a live
    application. Offered as an Envisage service by PluginManagementPlugin;
    the Manage Plugins dialog and the launch-restore hook use it."""

    groups = Dict(Str, Instance(PluginGroup))

    def _groups_default(self):
        """Built-in groups plus every group declared by an installed package's
        microdrop.plugins entry-point manifest. Manifest discovery reads TOML
        package data only (no plugin imports), so a broken installed plugin
        can't break startup; last writer wins on a name collision."""
        groups = {
            spec["name"]: PluginGroup(**spec) for spec in BUILTIN_PLUGIN_GROUPS
        }
        for manifest, dist_name in (
                entry_point_discovery.discover_entry_point_manifests()):
            self._add_manifest_groups(manifest, dist_name=dist_name, into=groups)
        return groups

    def _add_manifest_groups(self, manifest, dist_name="", into=None):
        """Create a PluginGroup per spec in ``manifest`` and put it in ``into``
        (defaults to self.groups)."""
        target = self.groups if into is None else into
        for spec in manifest.groups:
            target[spec.name] = PluginGroup(
                name=spec.name,
                label=spec.label,
                plugin_specs=list(spec.plugins),
                enabled_key=spec.enabled_key,
                post_enable_publish_topic=spec.post_enable_publish_topic,
                manifest_name=manifest.name,
                manifest_label=manifest.label,
                dist_name=dist_name,
                optional=spec.optional,
                toggle_label=spec.toggle_label or spec.label,
                manifest_version=manifest.version,
            )

    def register_manifest(self, manifest, dist_name=""):
        """Register a freshly-installed manifest's groups at runtime. Refuses
        (raises) if a colliding group name is currently loaded."""
        for spec in manifest.groups:
            existing = self.groups.get(spec.name)
            if existing is not None and existing.loaded:
                raise RuntimeError(
                    f"group '{spec.name}' is currently enabled; disable it "
                    f"before reinstalling")
        self._add_manifest_groups(manifest, dist_name=dist_name)

    #: The app's own distribution — its plugins are bundled (disable-only).
    APP_DIST_NAMES = frozenset({"microdrop-py", "microdrop_py"})

    @staticmethod
    def _norm_dist(name):
        return (name or "").strip().lower().replace("_", "-")

    def installed_plugins(self):
        """User-installed plugins (whose owning distribution is NOT the app's
        own), one entry per distinct manifest, as (name, label, dist_name,
        [group_names]) in discovery order. Built-in/bundled groups (no
        dist_name, or the app's own distribution) are excluded."""
        app = {self._norm_dist(n) for n in self.APP_DIST_NAMES}
        out = {}
        for group in self.groups.values():
            if self._norm_dist(group.dist_name) in app or not group.dist_name:
                continue
            entry = out.get(group.manifest_name)
            if entry is None:
                entry = (group.manifest_name,
                         group.manifest_label or group.manifest_name,
                         group.dist_name, [])
                out[group.manifest_name] = entry
            entry[3].append(group.name)
        return list(out.values())

    def deregister_plugin(self, manifest_name):
        """Drop every group owned by ``manifest_name`` from the registry and
        clear its persisted enabled flag. Used by uninstall."""
        for name in [n for n, g in self.groups.items()
                     if g.manifest_name == manifest_name]:
            group = self.groups.pop(name)
            if group.enabled_key:
                try:
                    if group.enabled_key in app_globals:
                        del app_globals[group.enabled_key]
                except Exception as e:
                    logger.debug(f"could not clear flag {group.enabled_key}: {e}")

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
                    plugin_class = _resolve_plugin_class(spec)
                except Exception as e:
                    logger.warning(f"adopt: cannot resolve {spec!r}: {e}")
                    continue
                plugin = _find_registered_plugin(application, plugin_class)
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
                # Belt-and-braces: if this plugin class is already registered
                # (startup composition raced ahead of adoption), ADOPT the
                # live instance — adding a second one duplicates its service
                # offers and crashes the mixin composition ("duplicate base
                # class" at the device controller's start).
                existing = _find_registered_plugin(application, factory)
                if existing is not None:
                    group.instances.append(existing)
                    logger.info(f"enable: adopted already-registered {existing.id}")
                    continue
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

"""Runtime hot load/unload of a *named group* of Envisage plugins.

Envisage supports adding/removing plugins at runtime, but three layers don't
self-heal (see the research notes): runtime ServiceOffers leak (CorePlugin
discards their ids), Pyface Tasks never adds a dock pane after the window is
shown, and a plugin's backend resources outlive a bare ``stop()``. This
orchestrator fills the first two gaps generically (service-id capture +
live dock-pane mount/unmount) and relies on each plugin's own ``stop()`` for
the third.

The pilot group is the optional magnet-peripheral trio. Ordering matters:
load backend -> column -> ui so the controller's services/topics exist before
the column/UI consume them; unload ui -> column -> backend so the pane and
status icon (which watch the connection state) die before the backend they
observe. The protocol tree's magnet column is NOT mounted here — it re-syncs
automatically when the column plugin's PROTOCOL_COLUMNS contribution
appears/withdraws (the tree plugin opted into connect_extension_point_traits).
"""

from traits.api import Bool, Dict, HasTraits, Instance, List, Str

from microdrop_application.consts import (
    MAGNET_BACKEND_GROUP, MAGNET_UI_GROUP,
    PERIPHERAL_BACKEND_ENABLED_KEY, PERIPHERAL_UI_ENABLED_KEY,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.tasks_runtime_helpers import (
    add_dock_pane_live, rebuild_menu_bar_live, remove_dock_pane_live,
)
from peripheral_controller.consts import (
    START_DEVICE_MONITORING as START_DEVICE_MONITORING_PERIPHERAL,
)
from logger.logger_service import get_logger

logger = get_logger(__name__)

app_globals = get_microdrop_redis_globals_manager()


class PluginGroup(HasTraits):
    """One named, ordered set of plugins that load/unload together."""

    name = Str()
    #: Plugin classes in load order (unloaded in reverse).
    plugin_factories = List()
    #: Live plugin instances while loaded (empty otherwise).
    instances = List()
    #: Service-registry ids registered while the group loaded, captured by a
    #: before/after snapshot so disable() can unregister exactly them
    #: (CorePlugin registers runtime ServiceOffers but discards their ids).
    service_ids = List()
    #: Ids of dock panes mounted live for this group, so disable() can remove
    #: the same panes it added.
    dock_pane_ids = List(Str)
    loaded = Bool(False)
    #: App-globals flag persisting this group's enabled state across runs.
    enabled_key = Str()
    #: Optional topic published (empty message) right after a successful
    #: enable — e.g. the backend group kicks off the magnet connection search.
    post_enable_publish_topic = Str()


class PluginGroupManager(HasTraits):
    """Loads/unloads named plugin groups against a live application.

    Offered as an Envisage service by MicrodropPlugin; the Tools -> Peripherals
    toggle and the launch-restore hook fetch it via get_service and call
    enable/disable.
    """

    groups = Dict(Str, Instance(PluginGroup))

    def _groups_default(self):
        # Importing plugin classes from a loader module is sanctioned here —
        # examples/plugin_consts.py already does exactly this.
        from peripheral_controller.plugin import PeripheralControllerPlugin
        from peripheral_protocol_controls.plugin import (
            PeripheralProtocolControlsPlugin,
        )
        from peripherals_ui.plugin import PeripheralUiPlugin

        ui = PluginGroup(
            name=MAGNET_UI_GROUP,
            plugin_factories=[
                PeripheralProtocolControlsPlugin,  # magnet protocol column
                PeripheralUiPlugin,                # dock pane + status icon + tools submenu
            ],
            enabled_key=PERIPHERAL_UI_ENABLED_KEY,
        )
        backend = PluginGroup(
            name=MAGNET_BACKEND_GROUP,
            plugin_factories=[PeripheralControllerPlugin],
            enabled_key=PERIPHERAL_BACKEND_ENABLED_KEY,
            post_enable_publish_topic=START_DEVICE_MONITORING_PERIPHERAL,
        )
        return {ui.name: ui, backend.name: backend}

    # --- public API --------------------------------------------------

    def is_loaded(self, group_name):
        group = self.groups.get(group_name)
        return bool(group is not None and group.loaded)

    def apply(self, task, desired):
        """Reconcile group load state to ``desired`` ({group_name: bool}).

        Enables run backend-before-UI (services/topics exist before the column/
        UI consume them); disables run UI-before-backend (UI dies before the
        backend it observes). Only groups whose desired state differs from
        their current state are touched."""
        for group_name in (MAGNET_BACKEND_GROUP, MAGNET_UI_GROUP):
            if desired.get(group_name) and not self.is_loaded(group_name):
                self.enable(task, group_name)
        for group_name in (MAGNET_UI_GROUP, MAGNET_BACKEND_GROUP):
            if (group_name in desired
                    and not desired[group_name]
                    and self.is_loaded(group_name)):
                self.disable(task, group_name)

    def enable(self, task, group_name):
        """Add + start every plugin in the group (in order), capture the
        services they register, and mount their dock panes onto the live
        window. Idempotent — a no-op if the group is already loaded."""
        group = self.groups.get(group_name)
        if group is None:
            logger.warning(f"enable: unknown plugin group '{group_name}'")
            return
        if group.loaded:
            logger.info(f"enable: group '{group_name}' already loaded")
            return

        application = task.window.application
        registry = application.service_registry
        before = set(registry._services.keys())

        for factory in group.plugin_factories:
            try:
                plugin = factory()
                application.add_plugin(plugin)
                application.start_plugin(plugin)
                group.instances.append(plugin)
                logger.info(f"enable: started {plugin.id}")
            except Exception:
                logger.exception(
                    f"enable: failed to load {getattr(factory, '__name__', factory)}"
                )

        group.service_ids = sorted(set(registry._services.keys()) - before)
        logger.info(f"enable: captured service ids {group.service_ids}")

        self._mount_dock_panes(task, group)

        # The plugin's menu contributions (e.g. the peripheral Search Connection
        # submenu) are gathered once at window creation; rebuild so they appear.
        try:
            rebuild_menu_bar_live(task.window, task, application)
        except Exception:
            logger.exception("enable: menu bar rebuild failed")

        # Optional post-enable kick — the backend group starts the magnet search.
        if group.post_enable_publish_topic:
            try:
                publish_message(topic=group.post_enable_publish_topic, message="")
                logger.info(f"enable: published {group.post_enable_publish_topic}")
            except Exception:
                logger.exception(
                    f"enable: failed to publish {group.post_enable_publish_topic}"
                )

        group.loaded = True
        if group.enabled_key:
            app_globals[group.enabled_key] = True
        logger.info(f"enable: group '{group_name}' loaded")

    def disable(self, task, group_name):
        """Reverse of enable: unmount dock panes, stop + remove every plugin
        (reverse order), and unregister the services captured at load. The
        protocol column withdraws itself via its extension-point contribution.
        Idempotent — a no-op if the group isn't loaded."""
        group = self.groups.get(group_name)
        if group is None:
            logger.warning(f"disable: unknown plugin group '{group_name}'")
            return
        if not group.loaded:
            logger.info(f"disable: group '{group_name}' not loaded")
            return

        application = task.window.application
        window = task.window

        # UI first: drop the panes before the backend they observe goes away.
        for pane_id in reversed(group.dock_pane_ids):
            try:
                remove_dock_pane_live(window, pane_id)
            except Exception:
                logger.exception(f"disable: failed to remove dock pane '{pane_id}'")
        group.dock_pane_ids = []

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
                logger.exception(f"disable: unregister_service failed for {service_id}")
        group.service_ids = []

        try:
            rebuild_menu_bar_live(window, task, application)
        except Exception:
            logger.exception("disable: menu bar rebuild failed")

        group.loaded = False
        if group.enabled_key:
            app_globals[group.enabled_key] = False
        logger.info(f"disable: group '{group_name}' unloaded")

    # --- helpers -----------------------------------------------------

    def _mount_dock_panes(self, task, group):
        """Mount every dock pane the group's started plugins contribute for
        this task. Pyface gathers panes once at window creation, so a plugin
        loaded afterwards needs its pane mounted explicitly."""
        window = task.window
        for plugin in group.instances:
            extensions = getattr(plugin, "contributed_task_extensions", None) or []
            for extension in extensions:
                ext_task_id = getattr(extension, "task_id", None)
                if ext_task_id and ext_task_id != task.id:
                    continue
                for factory in getattr(extension, "dock_pane_factories", []) or []:
                    try:
                        pane = add_dock_pane_live(window, task, factory)
                    except Exception:
                        logger.exception(
                            f"enable: failed to mount a dock pane for {plugin.id}"
                        )
                        continue
                    if pane is not None:
                        group.dock_pane_ids.append(pane.id)

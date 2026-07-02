"""PluginManagementPlugin — runtime plugin management.

Wires the reactive TASK_EXTENSIONS consumer (any plugin added to / removed
from the running application gets its dock panes mounted/unmounted and the
menu bar rebuilt automatically — the UI-side analogue of the message router's
reactive ACTOR_TOPIC_ROUTES handling), offers the PluginGroupManager service,
contributes the Tools ▸ Manage Plugins action, and restores each group's
persisted enabled state on launch.
"""
from envisage.api import Plugin, SERVICE_OFFERS, ServiceOffer, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import Any, Bool, List, Str, observe

from microdrop_application.consts import PKG as microdrop_application_PKG

from .consts import PKG, PKG_name
from .i_plugin_group_manager import IPluginGroupManager

from logger.logger_service import get_logger
logger = get_logger(__name__)


class PluginManagementPlugin(Plugin):
    """Reactive pane/menu mounting + the plugin-group manager service + UI."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    #: The task whose Tools menu we contribute to.
    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")

    my_service_offers = List(contributes_to=SERVICE_OFFERS)
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #: Cached singleton group manager (lazily built by the service factory).
    _manager = Any()

    #: View-layer controller that reactively mounts/unmounts dock panes +
    #: rebuilds the menu bar when TASK_EXTENSIONS change at runtime.
    _live_task_exts = Any()

    def start(self):
        """Listen for runtime TASK_EXTENSIONS changes so a hot-loaded plugin's
        dock panes get mounted and the menu bar rebuilt reactively (debounced).
        Uses the same registry mechanism connect_extension_point_traits() uses,
        applied as a consumer of the TasksApplication-owned TASK_EXTENSIONS
        extension point."""
        super().start()
        # Guard against a double start() (envisage starts a plugin once, but
        # add_extension_point_listener does not dedup — a second registration
        # would fire two reconciles per delta).
        if self._live_task_exts is None:
            from .live_task_extensions import LiveTaskExtensionsController
            self._live_task_exts = LiveTaskExtensionsController(
                application=self.application)
            self.application.add_extension_point_listener(
                self._on_task_extensions_changed, TASK_EXTENSIONS)

    def stop(self):
        super().stop()
        try:
            self.application.remove_extension_point_listener(
                self._on_task_extensions_changed, TASK_EXTENSIONS)
        except Exception as e:
            logger.debug(f"TASK_EXTENSIONS listener already removed: {e}")

    def _on_task_extensions_changed(self, registry, event):
        """Extension-registry listener: ``listener(registry, event)`` where
        ``event`` is an ExtensionPointChangedEvent carrying added/removed
        TaskExtensions. Forward the delta to the debounced controller."""
        if self._live_task_exts is not None:
            self._live_task_exts.on_changed(
                list(event.added), list(event.removed))

    # --- group-manager service -----------------------------------------

    def _my_service_offers_default(self):
        return [
            ServiceOffer(
                protocol=IPluginGroupManager,
                factory=self._create_plugin_group_manager,
            )
        ]

    def _create_plugin_group_manager(self, *args, **kwargs):
        """Factory for the group manager, cached on the plugin so every lookup
        shares one manager (and thus the loaded-group state)."""
        if self._manager is None:
            from .group_manager import PluginGroupManager
            self._manager = PluginGroupManager()
        return self._manager

    # --- menu contribution ----------------------------------------------

    def _contributed_task_extensions_default(self):
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        id="plugin_management.tools_actions",
                        factory=self._tools_actions_group,
                        path="MenuBar/Tools",
                    )
                ],
            )
        ]

    def _tools_actions_group(self):
        """Single Manage Plugins action in Tools."""
        from pyface.tasks.action.api import SGroup
        from .menus import ManagePluginsAction
        return SGroup(ManagePluginsAction(), id="plugin_management_actions")

    # --- launch restore ---------------------------------------------------

    #: True once the launch restore has run (it must run exactly once).
    _groups_restored = Bool(False)

    # COLON (not dot) observe: "application:application_initialized" fires only
    # when the application_initialized event fires. The dot form ALSO fires when
    # the intermediate `application` trait is assigned — i.e. at app
    # CONSTRUCTION, before the startup plugins are adoptable, which made this
    # restore enable() duplicate heater plugin instances and crash startup with
    # "duplicate base class HeaterMonitorMixinService".
    @observe("application:application_initialized")
    def _restore_groups_on_launch(self, event):
        """Adopt the startup-composed group plugins, then reconcile every
        group to its persisted enabled flag (default enabled) — so a group
        toggled off in a previous session stays off. Runs exactly once."""
        if self._groups_restored:
            return
        self._groups_restored = True
        manager = self._create_plugin_group_manager()
        try:
            manager.adopt_running(self.application)
            manager.restore_persisted(self.application)
        except Exception:
            logger.exception("plugin-group launch restore failed")

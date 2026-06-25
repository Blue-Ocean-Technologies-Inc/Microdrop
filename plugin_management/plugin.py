"""PluginManagementPlugin — self-contained runtime plugin management.

Offers the PluginGroupManager service (the hot load/unload + install/uninstall
orchestrator) and contributes the Install/Uninstall/Manage Plugins actions to
the microdrop task's Tools menu via TASK_EXTENSIONS (the manual_controls
pattern), so microdrop_application no longer wires any of this. Also restores
each plugin group whose persisted flag is set on launch.
"""

from envisage.api import Plugin, SERVICE_OFFERS, ServiceOffer, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import Any, List, Str, observe

from microdrop_application.consts import PKG as microdrop_application_PKG
from microdrop_application.helpers import get_microdrop_redis_globals_manager

from .consts import PKG, PKG_name
from .i_plugin_group_manager import IPluginGroupManager

from logger.logger_service import get_logger
logger = get_logger(__name__)


class PluginManagementPlugin(Plugin):
    """Contributes the plugin-management service + Tools menu actions."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    #: The task whose Tools menu we contribute to.
    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")

    my_service_offers = List(contributes_to=SERVICE_OFFERS)
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #: Cached singleton orchestrator (lazily built by the service factory).
    _manager = Any()

    #: View-layer controller that reactively mounts/unmounts dock panes +
    #: rebuilds the menu bar when TASK_EXTENSIONS change at runtime.
    _live_task_exts = Any()

    # --- reactive dock-pane / menu mounting --------------------------

    def start(self):
        """Listen for runtime TASK_EXTENSIONS changes so a hot-loaded plugin's
        dock panes get mounted and the menu bar rebuilt reactively (debounced),
        rather than the group manager driving it imperatively. Uses the same
        registry mechanism connect_extension_point_traits() uses, applied as a
        consumer of the TasksApplication-owned TASK_EXTENSIONS extension point."""
        super().start()
        from .live_task_extensions import LiveTaskExtensionsController
        self._live_task_exts = LiveTaskExtensionsController(self.application)
        self.application.add_extension_point_listener(
            self._on_task_extensions_changed, TASK_EXTENSIONS)

    def stop(self):
        super().stop()
        try:
            self.application.remove_extension_point_listener(
                self._on_task_extensions_changed, TASK_EXTENSIONS)
        except Exception:
            pass
        if self._live_task_exts is not None:
            self._live_task_exts.dispose()

    def _on_task_extensions_changed(self, registry, event):
        """Extension-registry listener: ``listener(registry, event)`` where
        ``event`` is an ExtensionPointChangedEvent carrying added/removed
        TaskExtensions. Forward the delta to the debounced controller."""
        if self._live_task_exts is not None:
            self._live_task_exts.on_changed(
                list(event.added), list(event.removed))

    # --- service offer -----------------------------------------------

    def _my_service_offers_default(self):
        return [
            ServiceOffer(
                protocol=IPluginGroupManager,
                factory=self._create_plugin_group_manager,
            )
        ]

    def _create_plugin_group_manager(self, *args, **kwargs):
        """Factory for the orchestrator, cached on the plugin so every lookup
        shares one manager (and thus the loaded-group state)."""
        if self._manager is None:
            from .group_manager import PluginGroupManager
            self._manager = PluginGroupManager()
        return self._manager

    # --- menu contribution -------------------------------------------

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
        """Install / Uninstall / Manage as one ordered group in Tools."""
        from pyface.tasks.action.api import SGroup
        from .menus import (
            InstallPluginAction, UninstallPluginAction, ManagePluginsAction,
        )
        return SGroup(
            InstallPluginAction(),
            UninstallPluginAction(),
            ManagePluginsAction(),
            id="plugin_management_actions",
        )

    # --- launch restore ----------------------------------------------

    @observe("application:active_window")
    def _on_active_window(self, event):
        """Restore enabled groups once a GUI window is available. Fires when
        the active window changes; the restore is idempotent (it only enables
        flagged groups not already loaded), so re-firing on a later window
        switch is a harmless no-op."""
        window = event.new
        if window is not None:
            self._restore_enabled_groups(window)

    def _restore_enabled_groups(self, window):
        """Make installed plugins importable, then re-enable every discovered
        group whose persisted flag is set (registration order). So the Manage
        Plugins checkboxes match what's actually loaded after a relaunch."""
        from . import paths

        paths.ensure_on_sys_path()
        manager = self.application.get_service(IPluginGroupManager)
        if manager is None:
            logger.warning("plugin restore: PluginGroupManager service not found")
            return
        task = window.active_task
        if task is None:
            logger.warning("plugin restore: no active task on window")
            return
        app_globals = get_microdrop_redis_globals_manager()
        for group_name, group in list(manager.groups.items()):
            if (group.enabled_key
                    and app_globals.get(group.enabled_key, False)
                    and not manager.is_loaded(group_name)):
                logger.info(
                    f"Restoring plugin group '{group_name}' from persisted flag"
                )
                manager.enable(task, group_name)

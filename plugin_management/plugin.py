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

    # --- service offer -----------------------------------------------

    def _my_service_offers_default(self):
        return [
            ServiceOffer(
                protocol="plugin_management.group_manager.PluginGroupManager",
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

    @observe("application:application_initialized")
    def _on_application_initialized(self, event):
        """Restore enabled groups once the GUI window exists."""
        window = self.application.active_window
        if window is None:
            self.application.on_trait_change(self._on_window_created, "active_window")
        else:
            self._restore_enabled_groups(window)

    def _on_window_created(self, window):
        if window is not None:
            self.application.on_trait_change(
                self._on_window_created, "active_window", remove=True)
            self._restore_enabled_groups(window)

    def _restore_enabled_groups(self, window):
        """Make installed plugins importable, then re-enable every discovered
        group whose persisted flag is set (registration order). So the Manage
        Plugins checkboxes match what's actually loaded after a relaunch."""
        from . import paths
        from .group_manager import PluginGroupManager

        paths.ensure_on_sys_path()
        manager = self.application.get_service(PluginGroupManager)
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

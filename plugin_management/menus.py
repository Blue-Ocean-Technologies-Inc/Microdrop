"""Tools-menu action for plugin management — a single Manage Plugins window.

Contributed to the microdrop task's MenuBar/Tools by PluginManagementPlugin via
TASK_EXTENSIONS. Heavy imports are deferred into ``perform``."""
from pyface.tasks.action.api import TaskAction

from logger.logger_service import get_logger

logger = get_logger(__name__)


class ManagePluginsAction(TaskAction):
    """Open the Manage Plugins window (install / uninstall / enable-disable)."""

    id = "manage_plugins_action"
    name = "&Manage Plugins…"

    def perform(self, event):
        task = event.task
        if task is None:
            logger.error("Manage Plugins: no task available")
            return
        from plugin_management.i_plugin_group_manager import IPluginGroupManager
        from plugin_management.manager_model import PluginManagerModel
        from plugin_management.manager_controller import PluginManagerController
        from plugin_management.manager_view import manager_view

        manager = task.window.application.get_service(IPluginGroupManager)
        if manager is None:
            logger.error("Manage Plugins: PluginGroupManager service not found")
            return

        model = PluginManagerModel(manager=manager)
        controller = PluginManagerController(task=task)
        # Edit the model with the controller as the Handler; the view's Items
        # resolve against the model, the buttons dispatch to controller methods.
        model.edit_traits(view=manager_view, handler=controller, kind="livemodal")


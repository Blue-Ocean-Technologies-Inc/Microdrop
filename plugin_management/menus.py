# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tools-menu action for plugin management — the Manage Plugins window.

Contributed to the microdrop task's MenuBar/Tools by PluginManagementPlugin
via TASK_EXTENSIONS."""
from pyface.tasks.action.api import TaskAction

from logger.logger_service import get_logger

from .i_plugin_group_manager import IPluginGroupManager
from .manage_model import ManagePluginsModel
from .manage_view import manage_plugins_view
from .manage_controller import ManagePluginsController

logger = get_logger(__name__)


class ManagePluginsAction(TaskAction):
    """Open the Manage Plugins window (enable/disable groups, install from the
    channel, uninstall)."""

    id = "manage_plugins_action"
    name = "&Manage Plugins…"

    def perform(self, event):
        task = event.task
        if task is None:
            logger.error("Manage Plugins: no task available")
            return

        application = task.window.application
        manager = application.get_service(IPluginGroupManager)
        if manager is None:
            logger.error("Manage Plugins: PluginGroupManager service not found")
            return

        model = ManagePluginsModel(manager=manager, application=application)
        controller = ManagePluginsController(model=model, task=task)
        model.edit_traits(view=manage_plugins_view, handler=controller)

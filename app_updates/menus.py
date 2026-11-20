# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Help > "Check for Updates…", and the one function that opens the Updates
dialog — for the menu and for the notice of a new release alike."""

# Enthought library imports.
from pyface.tasks.action.api import TaskAction

# Microdrop package imports.
from electrode_controller.consts import PKG as electrode_controller_PKG

# Local imports.
from .controller import UpdatesController
from .model import UpdatesModel
from .preferences import AppUpdatesPreferences
from .view import updates_view

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def open_updates_dialog(application):
    """Open the Updates dialog on the source checkout ``application`` runs."""
    # Every backend plugin set includes the electrode controller, so without
    # it the backend runs in a process of its own.
    backend_plugin = application.get_plugin(f"{electrode_controller_PKG}.plugin")

    model = UpdatesModel(
        preferences=AppUpdatesPreferences(preferences=application.preferences),
        frontend_only=backend_plugin is None,
    )
    model.refresh()

    controller = UpdatesController(model=model, application=application)
    model.edit_traits(view=updates_view, handler=controller)


class CheckForUpdatesAction(TaskAction):
    """Open the Updates dialog: the running version, the releases and their
    changelogs, and the update policy."""

    id = "check_for_updates_action"
    name = "Check for &Updates…"

    def perform(self, event):
        if event.task is None:
            logger.error("Check for Updates: no task available")

            return

        open_updates_dialog(event.task.window.application)

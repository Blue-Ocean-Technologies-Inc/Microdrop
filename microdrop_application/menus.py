# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.action.api import Action
from pyface.tasks.action.api import TaskWindowAction

# Microdrop package imports.
from microdrop_application.consts import ADVANCED_MODE_CHANGE, ADVANCED_MODE_KEY
from microdrop_application.helpers import (
    get_microdrop_redis_globals_manager,
    is_advanced_mode,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


class AdvancedModeAction(Action):
    id = "advanced_mode_action"
    name = "&Advanced Mode"
    style = "toggle"
    checked = is_advanced_mode()

    def perform(self, event):
        app_globals[ADVANCED_MODE_KEY] = self.checked

        logger.critical(
            "Microdrop Running in Advanced Mode!"
            if self.checked
            else "Microdrop Advanced Mode is Off."
        )

        publish_message(
            topic=ADVANCED_MODE_CHANGE,
            message=str(self.checked),
        )


class ResetLayoutAction(TaskWindowAction):
    """Restore the active task's default dock-pane layout.

    Panes the default layout does not name — including those hot-mounted by
    plugin groups — go back to their own dock area, hidden, exactly as on a
    first launch; the View menu toggles them back on. The window saves the
    result on exit like any other arrangement.
    """

    id = "reset_layout_action"
    name = "&Reset Layout"
    tooltip = "Restore the default arrangement of the dock panes"

    def perform(self, event=None):
        # The menu-bar rebuild on plugin hot-load clears `self.task` on this
        # shared action instance, so the click event's task is the reliable
        # source.
        task = getattr(event, "task", None) or self.task
        window = task.window if task is not None else None

        if window is None:
            logger.warning("Reset Layout: no task window to reset")

            return

        # Pyface re-docks the panes without touching their floating flag, so
        # an undocked pane would otherwise stay a free-floating window.
        for pane in window.dock_panes:
            pane.floating = False

        window.reset_layout()
        logger.info(f"Reset the layout of task '{task.id}' to its default")

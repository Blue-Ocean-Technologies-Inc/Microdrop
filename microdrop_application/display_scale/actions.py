# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Tools -> Display Scale... menu entry."""

# Enthought library imports.
from pyface.tasks.action.api import TaskAction

# Local imports.
from .consts import PKG
from .manager import display_scale_manager


class DisplayScaleAction(TaskAction):
    """Open the interface-scale slider."""

    id = f"{PKG}.display_scale"
    name = "&Display Scale..."

    def perform(self, event):
        # The menu bar is a class-level schema, so the controller does not
        # always get to inject `self.task`; the event's task, set by
        # TaskActionController.perform on every invocation, is reliable.
        task = getattr(event, "task", None) or self.task
        display_scale_manager.edit_scale(task.window.application)

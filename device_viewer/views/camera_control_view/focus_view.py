# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera panel's focus row: a manual focus slider with the lens's raw
position, and an Auto toggle where the camera has continuous auto focus.

Views a CameraFocusModel; standalone it only edits the model, while
CameraFocusHandler applies the edits through the camera controller."""

# Enthought library imports.
from traits.api import Instance
from traitsui.api import Handler, HGroup, Item, RangeEditor, UItem, View

# Local imports.
from ...controllers.camera_controller import CameraController


class CameraFocusHandler(Handler):
    """Applies the user's focus edits through the camera controller.

    Only editor writes pass through the ``*_setattr`` hooks, so the
    controller's own readbacks into the model are not applied back.
    """

    #: Applies the edits to the selected camera.
    controller = Instance(CameraController)

    def distance_setattr(self, info, focus, name, value):
        super().setattr(info, focus, name, value)
        self.controller.set_focus(value)

    def auto_setattr(self, info, focus, name, value):
        super().setattr(info, focus, name, value)
        self.controller.set_focus(None if value else focus.distance)


camera_focus_view = View(
    HGroup(
        Item(
            "distance",
            label="Focus",
            # Applied on release, not while dragging: a v4l2 focus write
            # runs a v4l2-ctl process.
            editor=RangeEditor(
                mode="slider",
                auto_set=False,
                low_label="Near",
                high_label="Far",
                format_str="%.2f",
            ),
            enabled_when="available and not auto",
            springy=True,
        ),
        UItem(
            "raw_position",
            style="readonly",
            visible_when="raw_position is not None",
            tooltip="Raw lens position (v4l2 focus_absolute)",
        ),
        Item(
            "auto",
            label="Auto",
            visible_when="auto_available",
            tooltip="Continuous auto focus",
        ),
    ),
)

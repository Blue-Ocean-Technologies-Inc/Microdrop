# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera panel's focus row: a manual focus slider applied live while
dragged, the lens's raw position (with its approximate focused distance
when calibrated), an Auto toggle where the camera has continuous auto
focus, and a one-shot Autofocus button.

Views a CameraFocusModel; standalone it only edits the model, while
CameraFocusHandler applies the edits through the camera controller, which
also observes the Autofocus button."""

# Enthought library imports.
from traits.api import Instance
from traitsui.api import (
    ButtonEditor,
    Handler,
    HGroup,
    Item,
    RangeEditor,
    UItem,
    VGroup,
    View,
)

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
        self.controller.request_focus(value)

    def auto_setattr(self, info, focus, name, value):
        super().setattr(info, focus, name, value)
        self.controller.set_focus(None if value else focus.distance)


camera_focus_view = View(
    VGroup(
        Item(
            "distance",
            label="Focus",
            # Live while dragging; the controller coalesces the writes, as
            # a v4l2 focus write runs a v4l2-ctl process.
            editor=RangeEditor(
                mode="slider",
                low_label="Near",
                high_label="Far",
                format_str="%.2f",
            ),
            enabled_when="available and not auto",
            springy=True,
        ),
        HGroup(
            UItem(
                "position_label",
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
            UItem(
                "autofocus_button",
                editor=ButtonEditor(label_value="autofocus_label"),
                enabled_when="autofocus_available and not auto and not autofocusing",
                tooltip="Focus once on the centre of the image (contrast sweep)",
                springy=True,
            ),
        ),
    ),
    # Resizable, or TraitsUI fixes the panel at its build-time size, before
    # the sidebar's text-button style makes the Autofocus button taller.
    resizable=True,
)

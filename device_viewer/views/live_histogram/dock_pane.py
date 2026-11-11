# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dock pane showing a realtime intensity histogram of the live camera
frame, an exposure aid like a camera's histogram display."""

# Enthought library imports.
from pyface.tasks.api import TraitsDockPane
from traits.api import Instance, observe

# Local imports.
from ...consts import PKG
from .controller import LiveHistogramController
from .model import LiveHistogramModel
from .view import LiveHistogramView


class LiveHistogramDockPane(TraitsDockPane):
    """Histogram of the device view's camera feed; samples only while shown."""

    id = PKG + ".live_histogram.dock_pane"
    name = "Live Histogram"

    view = LiveHistogramView

    model = Instance(LiveHistogramModel, ())

    #: Samples the device view's video item into the model.
    controller = Instance(LiveHistogramController)

    def _controller_default(self):
        return LiveHistogramController(
            model=self.model,
            get_video_item=self._device_view_video_item,
            get_dialog_parent=lambda: self.control,
        )

    def _device_view_video_item(self):
        """The device viewer pane's video item, or None until there is one."""
        window = self.task.window if self.task is not None else None

        if window is None:
            return None

        device_viewer_pane = window.get_dock_pane(PKG + ".dock_pane")

        return getattr(device_viewer_pane, "video_item", None)

    @observe("visible")
    def _sample_while_visible(self, event):
        self.controller.active = event.new

    def destroy(self):
        """Stop sampling and close the region picker before the pane's
        widgets go."""
        self.controller.active = False
        self.controller.close_region_picker()

        super().destroy()

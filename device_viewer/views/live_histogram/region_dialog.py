# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Live Histogram's region picker, modelled on the camera alignment
tool's device outline pane: one captured camera frame in the zoom/pan
view, where the user draws the rectangle the histogram covers.

- RegionPickerModel (``region.py``) — the region and the drag editing.
- region_picker_view — the module-level View: the readout and glyphs
  (fit, full frame, recapture) over the canvas, with OK and Cancel.
- RegionPickerController — owns the frame and the canvas: it draws the
  model's region, refits, and swaps in a fresh capture.

Open it modally: ``RegionPickerController(model=..., image=...,
capture_frame=...).edit_traits(view=region_picker_view, kind="livemodal")``;
``ui.result`` is True on OK, and the model then holds the picked region.
"""

# Enthought library imports.
from pyface.qt.QtGui import QImage, QPixmap
from traits.api import Callable, Instance, observe
from traitsui.api import (
    CancelButton,
    Controller,
    CustomEditor,
    HGroup,
    Item,
    Label,
    OKButton,
    UItem,
    VGroup,
    View,
    spring,
)

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_FIT_SCREEN, ICON_PHOTO_CAMERA, ICON_RESTORE

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import IconButtonEditor

# Local imports.
from ...consts import LIVE_HISTOGRAM_REGION_DIALOG_SIZE_PX
from .region import RegionPickerModel
from .region_overlay import RegionCanvas, RegionOverlay

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

CANVAS_MIN_SIZE_PX = (320, 240)

INSTRUCTIONS = (
    "Drag on the frame to draw the region; drag its edges or corners to "
    "resize it, or inside it to move it. Scroll to zoom, right-drag to pan."
)


def _canvas_factory(parent, editor):
    """CustomEditor factory: embed the controller's canvas widget."""
    return editor.value


# ------------------------------ View ------------------------------ #
region_picker_view = View(
    VGroup(
        HGroup(
            Item("region_text", style="readonly", label="Region"),
            spring,
            UItem(
                "fit",
                editor=IconButtonEditor(
                    glyph=ICON_FIT_SCREEN, tooltip="Fit the frame in the view"
                ),
            ),
            UItem(
                "full_frame",
                editor=IconButtonEditor(
                    glyph=ICON_RESTORE, tooltip="Cover the whole frame"
                ),
            ),
            UItem(
                "recapture",
                editor=IconButtonEditor(
                    glyph=ICON_PHOTO_CAMERA, tooltip="Capture a fresh frame"
                ),
            ),
        ),
        UItem("controller.canvas", editor=CustomEditor(_canvas_factory), springy=True),
        Label(INSTRUCTIONS),
    ),
    title="Histogram Region",
    buttons=[OKButton, CancelButton],
    width=LIVE_HISTOGRAM_REGION_DIALOG_SIZE_PX[0],
    height=LIVE_HISTOGRAM_REGION_DIALOG_SIZE_PX[1],
    resizable=True,
)


# --------------------------- Controller --------------------------- #
class RegionPickerController(Controller):
    """Shows the captured frame and the model's region on the canvas, and
    handles the frame glyphs."""

    model = Instance(RegionPickerModel)

    #: The captured frame the region is drawn on.
    image = Instance(QImage)

    #: Zero-arg callable returning a fresh frame QImage, or None when the
    #: camera has none.
    capture_frame = Callable()

    #: The zoomable frame the drags edit the region on.
    canvas = Instance(RegionCanvas)

    _overlay = Instance(RegionOverlay)

    def _canvas_default(self):
        canvas = RegionCanvas(QPixmap.fromImage(self.image), self.model)
        canvas.setMinimumSize(*CANVAS_MIN_SIZE_PX)

        self._overlay = RegionOverlay(canvas.scene())
        self._overlay.set_region(self.model.region, canvas.frame_size())

        return canvas

    @observe("model:region")
    def _draw_region(self, event):
        if self._overlay is not None:
            self._overlay.set_region(event.new, self.canvas.frame_size())

    @observe("model:fit")
    def _fit_frame(self, event):
        self.canvas.fit_frame()

    @observe("model:recapture")
    def _recapture_frame(self, event):
        """Swap in a fresh frame; the region keeps its place, as fractions."""
        image = self.capture_frame() if self.capture_frame else None

        if image is None or image.isNull():
            logger.warning("Histogram region recapture: the camera has no frame")

            return

        self.image = image
        self.model.frame_size = (image.width(), image.height())

        self.canvas.set_pixmap(QPixmap.fromImage(image))
        self._overlay.set_region(self.model.region, self.canvas.frame_size())
        self.canvas.fit_frame()

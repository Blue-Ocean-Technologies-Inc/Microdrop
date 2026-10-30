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
view, where the user draws the rectangle the histogram covers. The
window is non-modal, so the pane's plot keeps updating beside it; with
Live on, it follows the region as it is drawn.

- RegionPickerModel (``region.py``) — the region and the drag editing.
- region_picker_view — the module-level View: the readout and glyphs
  (live, fit, full frame, recapture) over the canvas, with OK and Cancel.
- RegionPickerController — owns the frame and the canvas: it draws the
  model's region, refits, swaps in a fresh capture, and writes the region
  into the histogram model: as it changes while Live is on, and on OK.
  Cancel, or closing the window, puts back the region the histogram had.

Open it with ``RegionPickerController(model=..., histogram=..., image=...,
capture_frame=...).edit_traits(view=region_picker_view, kind="live")``.
"""

# Enthought library imports.
from pyface.qt.QtGui import QImage, QPixmap
from traits.api import Callable, Instance, Tuple, observe
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
from microdrop_style.icons.icons import (
    ICON_FIT_SCREEN,
    ICON_PHOTO_CAMERA,
    ICON_PLAY,
    ICON_RESTORE,
)

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import IconButtonEditor, IconToggleEditor

# Local imports.
from ...consts import LIVE_HISTOGRAM_REGION_DIALOG_SIZE_PX
from .model import LiveHistogramModel
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
                "live",
                editor=IconToggleEditor(
                    on_glyph=ICON_PLAY,
                    off_glyph=ICON_PLAY,
                    tooltip="Apply the region to the histogram as you drag it",
                ),
            ),
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
    """Shows the captured frame and the model's region on the canvas,
    handles the frame glyphs, and applies the region to the histogram."""

    model = Instance(RegionPickerModel)

    #: The pane's histogram the picked region applies to.
    histogram = Instance(LiveHistogramModel)

    #: The histogram's region when the picker opened; Cancel restores it.
    _original_region = Tuple()

    #: The captured frame the region is drawn on.
    image = Instance(QImage)

    #: Zero-arg callable returning a fresh frame QImage, or None when the
    #: camera has none.
    capture_frame = Callable()

    #: The zoomable frame the drags edit the region on.
    canvas = Instance(RegionCanvas)

    _overlay = Instance(RegionOverlay)

    def traits_init(self):
        if self.histogram is not None:
            self._original_region = self.histogram.region

    def closed(self, info, is_ok):
        """OK keeps the picked region; Cancel and the window's close button
        put the original back, also after Live applied edits."""

        if self.histogram is not None:
            self.histogram.region = (
                self.model.region if is_ok else self._original_region
            )

        super().closed(info, is_ok)

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

    @observe("model:region, model:live")
    def _apply_live(self, event):
        """While Live is on, the histogram follows every edit; turning it
        off leaves the histogram as it was until OK."""

        if self.histogram is None:
            return

        if self.model.live:
            self.histogram.region = self.model.region

        elif event.name == "live":
            self.histogram.region = self._original_region

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

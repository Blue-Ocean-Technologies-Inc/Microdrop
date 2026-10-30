# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Sample the live camera feed into the Live Histogram model.

The device view's video item holds the frame on display, whatever its
source: QtMultimedia cameras and provider feeds (e.g. the fluorescence
plugin's ASI cameras) both push their preview frames into its sink. A timer
reads that frame, crops it to the histogram's region, downscales it, and
bins it — only while the pane is shown and not paused, so a hidden pane
costs nothing.

The controller also answers the pane's crop glyph: it captures one frame
and opens the region picker on it.
"""

# Standard library imports.
import time

# Third-party imports.
import numpy as np

# Enthought library imports.
from pyface.qt.QtCore import Qt, QTimer
from pyface.qt.QtGui import QImage
from traits.api import Bool, Callable, Float, HasTraits, Instance, observe

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import warning

# Local imports.
from ...consts import (
    LIVE_HISTOGRAM_IDLE_AFTER_S,
    LIVE_HISTOGRAM_IDLE_INTERVAL_MS,
    LIVE_HISTOGRAM_SAMPLE_WIDTH_PX,
)
from .model import LiveHistogramModel
from .region import RegionPickerModel, region_in_pixels
from .region_dialog import RegionPickerController, region_picker_view

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def sample_rgb_array(image, width=LIVE_HISTOGRAM_SAMPLE_WIDTH_PX):
    """Downscale a frame and return its pixels as an (H, W, 3) uint8 array.

    Fast (nearest-pixel) scaling keeps this a few ms on the GUI thread; a
    histogram needs the distribution, not every pixel.
    """

    if image.width() > width:
        image = image.scaledToWidth(width, Qt.TransformationMode.FastTransformation)

    image = image.convertToFormat(QImage.Format.Format_RGB888)
    height, row_bytes = image.height(), image.bytesPerLine()
    rows = np.frombuffer(image.constBits(), dtype=np.uint8, count=height * row_bytes)

    # Rows are padded to 4 bytes; the copy drops the padding and outlives
    # the QImage whose buffer the view borrows.
    pixels = rows.reshape(height, row_bytes)[:, : image.width() * 3]

    return pixels.reshape(height, image.width(), 3).copy()


class LiveHistogramController(HasTraits):
    """Poll the display item's current frame into the model while active."""

    #: The histogram state fed here.
    model = Instance(LiveHistogramModel)

    #: Returns the device view's QGraphicsVideoItem, or None while no device
    #: viewer pane has built one. Resolved on every tick: the camera widget
    #: may come later, and the pane may go.
    get_video_item = Callable()

    #: Returns the widget the region picker is parented to.
    get_dialog_parent = Callable()

    #: True while the pane is shown; sampling runs only then.
    active = Bool(False)

    #: Drives the sampling; built on first use.
    _timer = Instance(QTimer)

    #: monotonic() time the histogram last changed.
    _last_change_time = Float()

    def __timer_default(self):
        timer = QTimer()
        timer.timeout.connect(self.sample_frame)

        return timer

    @observe("active, model:[paused, rate_hz, has_frame, feed_idle]")
    def _schedule_sampling(self, event):
        """Run the timer at the chosen rate while there is something to
        sample, slowly while waiting for a feed, and not at all while the
        pane is hidden or paused."""

        if not self.active or self.model.paused:
            self._timer.stop()

            return

        if self.model.has_frame and not self.model.feed_idle:
            interval_ms = 1000 // self.model.rate_hz
        else:
            interval_ms = LIVE_HISTOGRAM_IDLE_INTERVAL_MS

        if self._timer.isActive() and self._timer.interval() == interval_ms:
            return

        self._timer.start(interval_ms)

    def sample_frame(self):
        """Bin the frame on display, or clear the model when there is none."""
        image = self._current_image()

        if image is None:
            if self.model.has_frame:
                self.model.clear()

            return

        frame_size = (image.width(), image.height())

        if self.model.region_active:
            image = image.copy(*region_in_pixels(self.model.region, frame_size))

        previous_counts = self.model.channel_counts
        self.model.update_from_rgb(sample_rgb_array(image), frame_size=frame_size)

        # Live sensors are never noise-free, so an unchanged histogram means
        # an unchanged frame: a stopped camera's last one.
        now = time.monotonic()

        if not np.array_equal(previous_counts, self.model.channel_counts):
            self._last_change_time = now

        self.model.feed_idle = (
            now - self._last_change_time > LIVE_HISTOGRAM_IDLE_AFTER_S
        )

    def _current_image(self):
        """The displayed frame as a QImage, or None without a showing feed."""
        video_item = self.get_video_item() if self.get_video_item else None

        if video_item is None:
            return None

        try:
            # A provider feed that stopped hides the item; its last frame
            # stays in the sink.
            if not video_item.isVisible():
                return None

            image = video_item.videoSink().videoFrame().toImage()
        except RuntimeError:
            # The device viewer pane was destroyed along with its item.
            logger.debug("Live histogram: the video item is gone")

            return None

        return None if image.isNull() else image

    def capture_frame(self):
        """ONE frame of the feed as a QImage copy, or None without one. The
        region picker calls this at open and on every recapture click."""
        image = self._current_image()

        return None if image is None else image.copy()

    @observe("model:pick_region")
    def open_region_picker(self, event=None):
        """Capture a frame and let the user mark the region on it; OK
        applies the region."""
        image = self.capture_frame()
        parent = self.get_dialog_parent() if self.get_dialog_parent else None

        if image is None:
            warning(
                parent,
                "No camera frame to capture yet — start the camera, then pick "
                "the region.",
                title="Histogram Region",
                cancel=False,
            )

            return

        picker = RegionPickerModel(
            region=self.model.region, frame_size=(image.width(), image.height())
        )

        if self.edit_region(picker, image, parent):
            self.model.region = picker.region

    def edit_region(self, picker, image, parent):
        """Show the region picker modally on ``image``; True on OK."""
        ui = RegionPickerController(
            model=picker, image=image, capture_frame=self.capture_frame
        ).edit_traits(view=region_picker_view, parent=parent, kind="livemodal")

        return ui.result

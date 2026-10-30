# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the Live Histogram pane: the binned intensities of the
latest camera frame and the exposure readouts derived from them. Mutated
only on the GUI thread (the controller's sampling timer)."""

# Third-party imports.
import numpy as np

# Enthought library imports.
from traits.api import (
    Array,
    Bool,
    Enum,
    Float,
    HasTraits,
    Int,
    Property,
    Range,
    Str,
    Tuple,
)

# Local imports.
from ...consts import (
    LIVE_HISTOGRAM_BINS,
    LIVE_HISTOGRAM_DEFAULT_RATE_HZ,
    LIVE_HISTOGRAM_LUMA_WEIGHTS,
    LIVE_HISTOGRAM_RANGE_PERCENTILES,
    LIVE_HISTOGRAM_RATE_BOUNDS_HZ,
)

#: Shown by the readouts while there is no frame to describe.
NO_READOUT = "–"


class LiveHistogramModel(HasTraits):
    """Histogram and exposure readouts of the live camera frame."""

    #: Pixel count per luma level (Rec. 601) of the latest frame.
    counts = Array(dtype=np.int64, shape=(LIVE_HISTOGRAM_BINS,))

    #: Pixel count per level of the red, green, and blue channels.
    channel_counts = Array(dtype=np.int64, shape=(3, LIVE_HISTOGRAM_BINS))

    #: Plot the luma histogram, or the three colour channels overlaid.
    channel_mode = Enum("luma", "rgb")

    #: Logarithmic count axis, which lifts sparse levels into view.
    log_y = Bool(False)

    #: Freeze the histogram on the current frame.
    paused = Bool(False)

    #: How often the live frame is sampled.
    rate_hz = Range(
        *LIVE_HISTOGRAM_RATE_BOUNDS_HZ, LIVE_HISTOGRAM_DEFAULT_RATE_HZ, mode="spinner"
    )

    #: Share (%) of the pixels in the darkest bin of the plotted histogram;
    #: in RGB mode, of the worst channel.
    clipped_low_pct = Property(Float, observe="counts, channel_counts, channel_mode")

    #: Share (%) of the pixels in the brightest bin, as above.
    clipped_high_pct = Property(Float, observe="counts, channel_counts, channel_mode")

    #: Mean luma of the frame (0-255).
    mean = Float()

    #: Luma levels below which 1 % and 99 % of the pixels fall.
    percentile_1 = Float()
    percentile_99 = Float()

    #: (width, height) of the sampled camera frame, in camera pixels.
    frame_size = Tuple(Int(), Int())

    #: True once a frame was binned; False while there is no camera feed.
    has_frame = Bool(False)

    #: True while the feed shows no new frames (e.g. a stopped camera leaves
    #: its last frame on display).
    feed_idle = Bool(False)

    #: Readouts, formatted for the pane.
    status_text = Property(Str, observe="has_frame, feed_idle, paused, frame_size")
    clipping_text = Property(
        Str, observe="has_frame, clipped_low_pct, clipped_high_pct"
    )
    mean_text = Property(Str, observe="has_frame, mean")
    range_text = Property(Str, observe="has_frame, percentile_1, percentile_99")

    def update_from_rgb(self, rgb, frame_size=None):
        """Bin an (H, W, 3) uint8 frame and refresh every readout.

        Parameters
        ----------
        rgb : numpy.ndarray
            The (downscaled) frame's pixels.
        frame_size : tuple of int, optional
            (width, height) of the camera frame ``rgb`` was sampled from;
            defaults to ``rgb``'s own.
        """
        height, width = rgb.shape[:2]
        pixel_count = height * width

        if pixel_count == 0:
            self.clear()

            return

        pixels = rgb.reshape(pixel_count, 3)

        channel_counts = np.stack(
            [
                np.bincount(pixels[:, channel], minlength=LIVE_HISTOGRAM_BINS)
                for channel in range(3)
            ]
        )

        # Integer Rec. 601: the weights sum to 256, so a grey pixel keeps its
        # level and the largest sum (65408) still fits in uint16.
        red_weight, green_weight, blue_weight = LIVE_HISTOGRAM_LUMA_WEIGHTS
        luma = (
            pixels[:, 0].astype(np.uint16) * red_weight
            + pixels[:, 1].astype(np.uint16) * green_weight
            + pixels[:, 2].astype(np.uint16) * blue_weight
            + 128
        ) >> 8
        counts = np.bincount(luma, minlength=LIVE_HISTOGRAM_BINS)

        cumulative = np.cumsum(counts)
        low_percentile, high_percentile = LIVE_HISTOGRAM_RANGE_PERCENTILES

        self.trait_set(
            counts=counts,
            channel_counts=channel_counts,
            mean=float(counts @ np.arange(LIVE_HISTOGRAM_BINS)) / pixel_count,
            percentile_1=float(
                np.searchsorted(cumulative, pixel_count * low_percentile / 100)
            ),
            percentile_99=float(
                np.searchsorted(cumulative, pixel_count * high_percentile / 100)
            ),
            frame_size=tuple(frame_size) if frame_size else (width, height),
            has_frame=True,
        )

    def clear(self):
        """Forget the last frame: an empty histogram and no readouts."""
        self.trait_set(
            counts=np.zeros(LIVE_HISTOGRAM_BINS, dtype=np.int64),
            channel_counts=np.zeros((3, LIVE_HISTOGRAM_BINS), dtype=np.int64),
            mean=0.0,
            percentile_1=0.0,
            percentile_99=0.0,
            frame_size=(0, 0),
            has_frame=False,
            feed_idle=False,
        )

    def plotted_counts(self):
        """The histogram(s) the plot shows: a (1, 256) luma or (3, 256) RGB
        array."""
        if self.channel_mode == "rgb":
            return self.channel_counts

        return self.counts[np.newaxis, :]

    # ------------------------------------------------------------------ #
    # Property getters                                                     #
    # ------------------------------------------------------------------ #
    def _get_clipped_low_pct(self):
        return self._end_bin_share_pct(0)

    def _get_clipped_high_pct(self):
        return self._end_bin_share_pct(-1)

    def _end_bin_share_pct(self, bin_index):
        """The largest share (%) of pixels in one end bin of the plotted
        histogram(s)."""
        plotted = self.plotted_counts()
        pixel_count = plotted[0].sum()

        if pixel_count == 0:
            return 0.0

        return float(plotted[:, bin_index].max()) * 100 / pixel_count

    def _get_status_text(self):
        if not self.has_frame:
            return "No camera feed"

        width, height = self.frame_size
        state = "paused" if self.paused else "idle" if self.feed_idle else "live"

        return f"{width} × {height}, {state}"

    def _get_clipping_text(self):
        if not self.has_frame:
            return NO_READOUT

        return (
            f"{self.clipped_low_pct:.1f} % dark, {self.clipped_high_pct:.1f} % bright"
        )

    def _get_mean_text(self):
        if not self.has_frame:
            return NO_READOUT

        return f"{self.mean:.1f}"

    def _get_range_text(self):
        if not self.has_frame:
            return NO_READOUT

        return f"{self.percentile_1:.0f} – {self.percentile_99:.0f}"

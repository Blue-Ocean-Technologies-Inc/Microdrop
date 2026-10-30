# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Live Histogram pane: the model's binning and readouts on synthetic frames,
the plot painting in both modes, and the controller's frame sampling."""

# Third-party imports.
import numpy as np
import pytest

# Enthought library imports.
from pyface.qt.QtGui import QColor, QImage
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from device_viewer.consts import LIVE_HISTOGRAM_BINS, LIVE_HISTOGRAM_SAMPLE_WIDTH_PX
from device_viewer.views.live_histogram.controller import (
    LiveHistogramController,
    sample_rgb_array,
)
from device_viewer.views.live_histogram.histogram_widget import LiveHistogramWidget
from device_viewer.views.live_histogram.model import LiveHistogramModel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def gradient_frame(height=4):
    """Every grey level once per row: a perfectly flat histogram."""
    levels = np.arange(LIVE_HISTOGRAM_BINS, dtype=np.uint8)
    row = np.repeat(levels[:, np.newaxis], 3, axis=1)

    return np.repeat(row[np.newaxis, :, :], height, axis=0)


def test_all_black_frame_is_fully_clipped_dark():
    model = LiveHistogramModel()

    model.update_from_rgb(np.zeros((10, 20, 3), dtype=np.uint8))

    assert model.has_frame
    assert model.frame_size == (20, 10)
    assert model.counts[0] == 200
    assert model.clipped_low_pct == pytest.approx(100.0)
    assert model.clipped_high_pct == 0.0
    assert model.mean == 0.0
    assert model.percentile_99 == 0.0


def test_all_white_frame_is_fully_clipped_bright():
    model = LiveHistogramModel()

    model.update_from_rgb(np.full((10, 20, 3), 255, dtype=np.uint8))

    assert model.counts[-1] == 200
    assert model.clipped_high_pct == pytest.approx(100.0)
    assert model.clipping_text == "0.0 % dark, 100.0 % bright"


def test_grey_gradient_gives_flat_luma_and_channel_counts():
    model = LiveHistogramModel()

    model.update_from_rgb(gradient_frame(height=4), frame_size=(1920, 1080))

    assert np.all(model.counts == 4)
    assert np.all(model.channel_counts == 4)
    assert model.mean == pytest.approx(127.5)
    assert model.percentile_1 == pytest.approx(2.0, abs=1)
    assert model.percentile_99 == pytest.approx(253.0, abs=1)
    assert model.frame_size == (1920, 1080)


def test_channel_counts_separate_the_colours():
    model = LiveHistogramModel()
    frame = np.zeros((2, 5, 3), dtype=np.uint8)
    frame[..., 0] = 255
    frame[..., 1] = 100

    model.update_from_rgb(frame)

    red, green, blue = model.channel_counts
    assert red[255] == 10
    assert green[100] == 10
    assert blue[0] == 10

    # Luma of (255, 100, 0) is mid-grey, but the RGB view reports the clipped
    # channels at both ends.
    assert model.clipped_high_pct == 0.0

    model.channel_mode = "rgb"

    assert model.clipped_high_pct == pytest.approx(100.0)
    assert model.clipped_low_pct == pytest.approx(100.0)


def test_clear_drops_the_frame():
    model = LiveHistogramModel()
    model.update_from_rgb(gradient_frame())

    model.clear()

    assert not model.has_frame
    assert model.counts.sum() == 0
    assert model.status_text == "No camera feed"
    assert model.clipping_text == "–"


@pytest.mark.parametrize("channel_mode", ["luma", "rgb"])
@pytest.mark.parametrize("log_y", [False, True])
def test_plot_paints_in_every_mode(qapp, channel_mode, log_y):
    model = LiveHistogramModel(channel_mode=channel_mode, log_y=log_y)
    widget = LiveHistogramWidget(model)
    widget.resize(300, 150)

    # Empty, then a clipped frame (cues lit), then a frame with no interior
    # counts (the scale falls back to the end bins).
    assert not widget.grab().isNull()

    model.update_from_rgb(gradient_frame())
    assert not widget.grab().isNull()

    model.update_from_rgb(np.zeros((4, 4, 3), dtype=np.uint8))
    assert not widget.grab().isNull()


def test_sample_rgb_array_downscales_and_drops_row_padding(qapp):
    # 1001 px wide: RGB888 rows are padded, so a naive reshape would shear.
    image = QImage(1001, 501, QImage.Format.Format_ARGB32)
    image.fill(QColor(10, 20, 30))

    rgb = sample_rgb_array(image)

    assert rgb.dtype == np.uint8
    assert rgb.shape[1] == LIVE_HISTOGRAM_SAMPLE_WIDTH_PX
    assert rgb.shape[2] == 3
    assert np.all(rgb == [10, 20, 30])

    # An odd-width small frame is used as is.
    small = QImage(7, 3, QImage.Format.Format_RGB32)
    small.fill(QColor(255, 0, 128))

    assert sample_rgb_array(small).shape == (3, 7, 3)
    assert np.all(sample_rgb_array(small) == [255, 0, 128])


class StubVideoItem:
    """Stands in for a QGraphicsVideoItem: its sink's frame is an image."""

    def __init__(self, image, visible=True):
        self.image = image
        self.visible = visible

    def isVisible(self):
        return self.visible

    def videoSink(self):
        return self

    def videoFrame(self):
        return self

    def toImage(self):
        return self.image


def test_controller_samples_the_video_item_and_clears_without_one(qapp):
    image = QImage(640, 480, QImage.Format.Format_RGB32)
    image.fill(QColor(255, 255, 255))
    video_item = StubVideoItem(image)
    model = LiveHistogramModel()
    controller = LiveHistogramController(model=model, get_video_item=lambda: video_item)

    controller.sample_frame()

    assert model.has_frame
    assert model.frame_size == (640, 480)
    assert model.clipped_high_pct == pytest.approx(100.0)

    # A stopped provider feed hides the item, keeping its last frame.
    video_item.visible = False
    controller.sample_frame()

    assert not model.has_frame

    # No device viewer pane, or no frame yet.
    controller.get_video_item = lambda: None
    controller.sample_frame()

    assert not model.has_frame

    controller.get_video_item = lambda: StubVideoItem(QImage())
    controller.sample_frame()

    assert not model.has_frame


def test_controller_timer_runs_only_while_active_and_not_paused(qapp):
    model = LiveHistogramModel()
    controller = LiveHistogramController(model=model, get_video_item=lambda: None)

    assert not controller._timer.isActive()

    controller.active = True

    assert controller._timer.isActive()

    model.paused = True

    assert not controller._timer.isActive()

    model.paused = False
    controller.active = False

    assert not controller._timer.isActive()

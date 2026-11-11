# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Live Histogram region of interest: the rectangle maths, the picker's
drag editing, the controller's cropping and pick flow, and the picker
dialog's frame handling (built, never shown)."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtGui import QColor, QImage, QPainter
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from device_viewer.consts import (
    LIVE_HISTOGRAM_FULL_FRAME_REGION,
    LIVE_HISTOGRAM_REGION_MIN_FRACTION,
)
from device_viewer.views.live_histogram import controller as controller_module
from device_viewer.views.live_histogram.controller import LiveHistogramController
from device_viewer.views.live_histogram.model import LiveHistogramModel
from device_viewer.views.live_histogram.region import (
    ALL_SIDES,
    RegionPickerModel,
    clamp_region,
    dragged_region,
    format_region,
    grabbed_sides,
    region_in_pixels,
)
from device_viewer.views.live_histogram.region_dialog import RegionPickerController

TOLERANCE = (0.02, 0.02)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class StubVideoItem:
    """Stands in for a QGraphicsVideoItem: its sink's frame is an image."""

    def __init__(self, image):
        self.image = image

    def isVisible(self):
        return True

    def videoSink(self):
        return self

    def videoFrame(self):
        return self

    def toImage(self):
        return self.image


def bright_quadrant_image(width=640, height=480):
    """A black frame with a white top-left quadrant."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 0, 0))

    painter = QPainter(image)
    painter.fillRect(0, 0, width // 2, height // 2, QColor(255, 255, 255))
    painter.end()

    return image


# ---------------------------------------------------------------------- #
# Rectangle maths                                                         #
# ---------------------------------------------------------------------- #
def test_clamp_region_orders_clips_and_grows_small_sides():
    assert clamp_region((0.8, 0.9, 0.2, 0.1)) == pytest.approx((0.2, 0.1, 0.8, 0.9))
    assert clamp_region((-0.5, -1.0, 1.5, 2.0)) == LIVE_HISTOGRAM_FULL_FRAME_REGION

    left, top, right, bottom = clamp_region((0.5, 0.999, 0.5, 1.0))

    assert right - left == pytest.approx(LIVE_HISTOGRAM_REGION_MIN_FRACTION)
    assert left == pytest.approx(0.5 - LIVE_HISTOGRAM_REGION_MIN_FRACTION / 2)

    # Grown inside the frame, not past its edge.
    assert bottom == pytest.approx(1.0)
    assert bottom - top == pytest.approx(LIVE_HISTOGRAM_REGION_MIN_FRACTION)


def test_region_in_pixels_rounds_and_keeps_a_pixel():
    assert region_in_pixels((0.25, 0.5, 0.75, 1.0), (640, 480)) == (160, 240, 320, 240)
    assert region_in_pixels((0.5, 0.5, 0.5, 0.5), (10, 10)) == (5, 5, 1, 1)
    assert region_in_pixels((1.0, 1.0, 1.0, 1.0), (10, 10)) == (9, 9, 1, 1)


def test_format_region():
    assert format_region(LIVE_HISTOGRAM_FULL_FRAME_REGION, (640, 480)) == "Full frame"
    assert (
        format_region((0.25, 0.5, 0.75, 1.0), (640, 480))
        == "320 × 240 px at (160, 240)"
    )
    assert format_region((0.25, 0.5, 0.75, 1.0), (0, 0)) == "50 × 50 % of the frame"


def test_grabbed_sides():
    region = (0.2, 0.2, 0.6, 0.6)

    assert grabbed_sides(region, (0.2, 0.4), TOLERANCE) == (0,)
    assert grabbed_sides(region, (0.4, 0.61), TOLERANCE) == (3,)
    assert grabbed_sides(region, (0.61, 0.19), TOLERANCE) == (1, 2)
    assert grabbed_sides(region, (0.4, 0.4), TOLERANCE) == ALL_SIDES
    assert grabbed_sides(region, (0.9, 0.9), TOLERANCE) == ()

    # Beyond an edge's span, its line does not grab.
    assert grabbed_sides(region, (0.2, 0.9), TOLERANCE) == ()

    # A full-frame region cannot move: a press inside starts a fresh one,
    # while its edges still grab.
    assert grabbed_sides(LIVE_HISTOGRAM_FULL_FRAME_REGION, (0.5, 0.5), TOLERANCE) == ()
    assert grabbed_sides(LIVE_HISTOGRAM_FULL_FRAME_REGION, (0.0, 0.5), TOLERANCE) == (
        0,
    )


def test_dragged_region_resizes_crosses_over_and_moves_within_the_frame():
    region = (0.2, 0.2, 0.6, 0.6)

    assert dragged_region(region, (2,), (0.6, 0.4), (0.8, 0.1)) == pytest.approx(
        (0.2, 0.2, 0.8, 0.6)
    )

    # Pulling the left side past the right one swaps them.
    assert dragged_region(region, (0,), (0.2, 0.4), (0.9, 0.4)) == pytest.approx(
        (0.6, 0.2, 0.9, 0.6)
    )

    # A move keeps the size and stops at the frame's edge.
    assert dragged_region(region, ALL_SIDES, (0.4, 0.4), (1.0, 0.3)) == pytest.approx(
        (0.6, 0.1, 1.0, 0.5)
    )


# ---------------------------------------------------------------------- #
# Picker model                                                            #
# ---------------------------------------------------------------------- #
def test_picker_draws_a_fresh_region_from_the_press():
    picker = RegionPickerModel(frame_size=(640, 480))

    picker.begin_drag((0.7, 0.6), TOLERANCE)
    picker.drag_to((0.3, 0.2))
    picker.end_drag()

    assert picker.region == pytest.approx((0.3, 0.2, 0.7, 0.6))
    assert picker.region_text == "256 × 192 px at (192, 96)"

    # Drags after a release do nothing.
    picker.drag_to((0.9, 0.9))

    assert picker.region == pytest.approx((0.3, 0.2, 0.7, 0.6))


def test_picker_ignores_a_click_and_resets_to_the_full_frame():
    picker = RegionPickerModel(region=(0.2, 0.2, 0.6, 0.6))

    # A press outside the region, barely moved: no fresh region.
    picker.begin_drag((0.9, 0.9), TOLERANCE)
    picker.drag_to((0.905, 0.9))
    picker.end_drag()

    assert picker.region == (0.2, 0.2, 0.6, 0.6)

    picker.begin_drag((0.4, 0.4), TOLERANCE)
    picker.drag_to((0.5, 0.45))
    picker.end_drag()

    assert picker.region == pytest.approx((0.3, 0.25, 0.7, 0.65))

    picker.full_frame = True

    assert picker.region == LIVE_HISTOGRAM_FULL_FRAME_REGION


# ---------------------------------------------------------------------- #
# Live model and controller                                               #
# ---------------------------------------------------------------------- #
def test_model_region_state_and_readout():
    model = LiveHistogramModel()

    assert not model.region_active
    assert model.region_text == "Full frame"

    model.region = (0.0, 0.0, 0.5, 0.5)
    model.frame_size = (1920, 1080)

    assert model.region_active
    assert model.region_text == "960 × 540 px at (0, 0)"

    model.clear_region = True

    assert not model.region_active


def test_controller_bins_only_the_region(qapp):
    model = LiveHistogramModel()
    controller = LiveHistogramController(
        model=model, get_video_item=lambda: StubVideoItem(bright_quadrant_image())
    )

    controller.sample_frame()

    assert model.mean == pytest.approx(255 / 4, abs=1)

    model.region = (0.0, 0.0, 0.5, 0.5)
    controller.sample_frame()

    assert model.mean == pytest.approx(255)

    # The readouts still describe the whole camera frame.
    assert model.frame_size == (640, 480)

    model.region = (0.5, 0.5, 1.0, 1.0)
    controller.sample_frame()

    assert model.mean == pytest.approx(0)


def open_picker(qapp):
    """A histogram controller on a stub feed, its picker opened (offscreen)."""
    model = LiveHistogramModel()
    controller = LiveHistogramController(
        model=model, get_video_item=lambda: StubVideoItem(bright_quadrant_image())
    )

    model.pick_region = True

    return model, controller


def test_picker_applies_the_region_on_ok_only_while_live_is_off(qapp):
    model, controller = open_picker(qapp)
    picker = controller._region_picker

    assert controller.region_picker_open
    assert picker.region == LIVE_HISTOGRAM_FULL_FRAME_REGION
    assert picker.frame_size == (640, 480)

    picker.region = (0.1, 0.2, 0.3, 0.4)

    assert not model.region_active

    controller._region_picker_ui.control.accept()

    assert not controller.region_picker_open
    assert model.region == pytest.approx((0.1, 0.2, 0.3, 0.4))

    # The next picker opens on the current region.
    model.pick_region = True

    assert controller._region_picker.region == pytest.approx((0.1, 0.2, 0.3, 0.4))

    controller.close_region_picker()


def test_live_picker_applies_as_it_edits_and_cancel_restores(qapp):
    model, controller = open_picker(qapp)
    picker = controller._region_picker
    ui = controller._region_picker_ui

    picker.region = (0.1, 0.2, 0.3, 0.4)
    picker.live = True

    assert model.region == pytest.approx((0.1, 0.2, 0.3, 0.4))

    picker.region = (0.5, 0.5, 0.9, 0.9)

    assert model.region == pytest.approx((0.5, 0.5, 0.9, 0.9))

    # Live off again: the histogram goes back until OK.
    picker.live = False

    assert not model.region_active

    picker.live = True

    # A second crop click raises the open picker rather than opening one.
    model.pick_region = True

    assert controller._region_picker_ui is ui

    ui.control.reject()

    assert not controller.region_picker_open
    assert model.region == LIVE_HISTOGRAM_FULL_FRAME_REGION

    # The Live choice carries over to the next picker.
    model.pick_region = True

    assert controller._region_picker.live

    controller._region_picker.full_frame = True
    controller._region_picker.region = (0.0, 0.0, 0.5, 0.5)

    assert model.region == pytest.approx((0.0, 0.0, 0.5, 0.5))

    # Closing the window (or the pane) acts as Cancel.
    controller.close_region_picker()

    assert model.region == LIVE_HISTOGRAM_FULL_FRAME_REGION


def test_pick_flow_warns_without_a_frame(qapp, monkeypatch):
    model = LiveHistogramModel()
    controller = LiveHistogramController(model=model, get_video_item=lambda: None)
    warnings = []

    monkeypatch.setattr(
        controller_module, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    model.pick_region = True

    assert len(warnings) == 1
    assert not controller.region_picker_open


def test_picker_dialog_draws_the_region_and_recaptures(qapp):
    picker = RegionPickerModel(region=(0.25, 0.25, 0.75, 0.75), frame_size=(640, 480))
    dialog = RegionPickerController(
        model=picker,
        image=bright_quadrant_image(),
        capture_frame=lambda: bright_quadrant_image(320, 200),
    )

    canvas = dialog.canvas

    assert dialog._overlay.frame_rect().getRect() == (160, 120, 320, 240)

    picker.region = (0.0, 0.0, 0.5, 0.5)

    assert dialog._overlay.frame_rect().getRect() == (0, 0, 320, 240)

    picker.recapture = True

    assert picker.frame_size == (320, 200)
    assert canvas.frame_size() == (320, 200)
    assert dialog._overlay.frame_rect().getRect() == (0, 0, 160, 100)

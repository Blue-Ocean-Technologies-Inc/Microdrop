# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera-alignment dialog links the corner dots of its two panes:
the dot hovered or pressed in one pane is highlighted in both, through
CameraAlignmentModel.active_point_index. Headless; no exec()."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtCore import QRectF, Qt
from pyface.qt.QtGui import QImage
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from device_viewer.preferences import DeviceViewerPreferences
from device_viewer.views.camera_alignment_view.alignment_dialog import (
    CameraAlignmentController,
    CameraAlignmentModel,
)
from device_viewer.views.camera_alignment_view.alignment_panes import (
    EndpointPane,
    OutlinePane,
)
from device_viewer.views.camera_alignment_view.alignment_settings import (
    AlignmentSettingsModel,
)


def _image():
    image = QImage(200, 100, QImage.Format_RGB32)
    image.fill(Qt.gray)

    return image


@pytest.fixture
def model():
    QApplication.instance() or QApplication([])

    model = CameraAlignmentModel(
        outline_pane=OutlinePane(capture_frame=_image),
        endpoint_pane=EndpointPane(
            device_image=_image(), scene_rect=QRectF(0, 0, 200, 100)
        ),
        settings=AlignmentSettingsModel(
            preferences=DeviceViewerPreferences(preferences=Preferences())
        ),
    )
    # Held for the test: its observers do the cross-pane linking.
    _controller = CameraAlignmentController(model=model)

    yield model


def _active_flags(pane):
    return [handle.is_active() for handle in pane._overlay._handles]


def test_model_index_highlights_the_dot_in_both_panes(model):
    model.active_point_index = 2

    assert _active_flags(model.outline_pane) == [False, False, True, False]
    assert _active_flags(model.endpoint_pane) == [False, False, True, False]

    model.active_point_index = -1

    assert not any(_active_flags(model.outline_pane))
    assert not any(_active_flags(model.endpoint_pane))


def test_hovering_a_dot_in_one_pane_highlights_its_match(model):
    handle = model.outline_pane._overlay._handles[1]

    handle._report_active(True)

    assert model.active_point_index == 1
    assert _active_flags(model.endpoint_pane) == [False, True, False, False]

    handle._report_active(False)

    assert model.active_point_index == -1
    assert not any(_active_flags(model.endpoint_pane))


def test_active_dot_grows_a_halo(model):
    handle = model.endpoint_pane._overlay._handles[0]
    normal = handle.boundingRect().width()

    model.active_point_index = 0

    assert handle.boundingRect().width() > normal


def _ring_of_dot_zero(pane):
    handle = pane._overlay._handles[0]

    return handle.active_ring_radius(), handle.active_ring_color().name()


def test_highlight_settings_restyle_the_ring_in_both_panes(model):
    model.active_point_index = 0
    radius, _ = _ring_of_dot_zero(model.outline_pane)

    model.settings.active_ring_scale = 3.0
    model.settings.active_color = (0.0, 0.0, 1.0)

    for pane in (model.outline_pane, model.endpoint_pane):
        new_radius, colour = _ring_of_dot_zero(pane)

        assert new_radius > radius
        assert colour == "#0000ff"


def test_dots_are_numbered_and_follow_the_dot_size(model):
    handles = model.endpoint_pane._overlay._handles
    size = handles[0].label_pixel_size()

    model.settings.handle_radius_px = 20

    assert [handle.label_text() for handle in handles] == ["1", "2", "3", "4"]
    assert handles[0].label_pixel_size() > size

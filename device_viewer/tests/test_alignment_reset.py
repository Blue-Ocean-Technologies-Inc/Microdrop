# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The alignment panes' Reset buttons: the outline pane returns to its
fresh state; the endpoint pane, once confirmed, forgets the saved
endpoint and returns to the default grid. Headless; no exec()."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import QRectF, Qt
from pyface.qt.QtGui import QImage
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from device_viewer.utils.camera_endpoints import CameraEndpointStore
from device_viewer.views.camera_alignment_view import alignment_panes
from device_viewer.views.camera_alignment_view.alignment_panes import (
    EndpointPane,
    OutlinePane,
)
from microdrop_application.dialogs.pyface_wrapper import NO, YES

#: TL/TR/BR/BL of a 200x100 image inset by a quarter / by 5%.
OUTLINE_DEFAULT = [[50, 25], [150, 25], [150, 75], [50, 75]]
ENDPOINT_DEFAULT = [[10, 5], [190, 5], [190, 95], [10, 95]]
SAVED = [[20.0, 10.0], [180.0, 10.0], [180.0, 90.0], [20.0, 90.0]]


def _image():
    QApplication.instance() or QApplication([])
    image = QImage(200, 100, QImage.Format_RGB32)
    image.fill(Qt.gray)

    return image


def _rounded(quad):
    return [[round(x, 6), round(y, 6)] for x, y in quad]


def test_outline_reset_restores_the_fresh_pane():
    pane = OutlinePane(capture_frame=_image)
    pane.rotate = True
    pane.flip_vertical = True
    pane.image_locked = True
    pane._overlay.set_quad([[1, 1], [9, 1], [9, 9], [1, 9]])

    pane.reset = True

    assert pane.orientation.trait_get(
        "quarter_turns", "flip_horizontal", "flip_vertical"
    ) == {"quarter_turns": 0, "flip_horizontal": False, "flip_vertical": False}
    assert not pane.image_locked
    assert _rounded(pane.shown_quad()) == OUTLINE_DEFAULT
    assert pane.canvas._pixmap_item.pixmap().size().toTuple() == (200, 100)


@pytest.fixture
def endpoint_pane(tmp_path):
    store = CameraEndpointStore(path=tmp_path / "camera_endpoints.json")
    store.save("chip", SAVED)

    return EndpointPane(
        device_image=_image(),
        scene_rect=QRectF(0, 0, 200, 100),
        initial_scene_quad=store.load("chip"),
        device_name="chip",
        endpoint_store=store,
    )


def test_confirmed_endpoint_reset_clears_the_store_and_dots(endpoint_pane, monkeypatch):
    monkeypatch.setattr(alignment_panes, "confirm", lambda *a, **k: YES)

    endpoint_pane.reset = True

    assert endpoint_pane.endpoint_store.load("chip") is None
    assert _rounded(endpoint_pane.shown_quad()) == ENDPOINT_DEFAULT


def test_declined_endpoint_reset_changes_nothing(endpoint_pane, monkeypatch):
    monkeypatch.setattr(alignment_panes, "confirm", lambda *a, **k: NO)

    endpoint_pane.reset = True

    assert endpoint_pane.endpoint_store.load("chip") == SAVED
    assert _rounded(endpoint_pane.shown_quad()) == SAVED

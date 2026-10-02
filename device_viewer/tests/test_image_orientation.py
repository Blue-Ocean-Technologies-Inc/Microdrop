# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""ImageOrientation folds display rotates/flips into one canonical form,
and the alignment dialog's outline pane shows the frame through it while
reporting the marked quad in raw camera pixels."""

# Standard library imports.
import itertools

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QColor, QImage
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from device_viewer.models.image_orientation import ImageOrientation
from device_viewer.views.camera_alignment_view.alignment_panes import OutlinePane

SIZE = (200, 100)
POINT = (30, 10)


def _display_ops_applied(ops, point, size):
    """Apply rotate/flip ops one by one to a point on the DISPLAYED image."""
    (x, y), (width, height) = point, size

    for op in ops:
        if op == "rotate":
            x, y = height - y, x
            width, height = height, width

        elif op == "flip_h":
            x = width - x

        else:
            y = height - y

    return [x, y]


def _apply(orientation, ops):
    for op in ops:
        if op == "rotate":
            orientation.rotate_clockwise()

        else:
            orientation.flip(horizontal=op == "flip_h")


@pytest.mark.parametrize(
    "ops", list(itertools.product(["rotate", "flip_h", "flip_v"], repeat=3))
)
def test_canonical_form_matches_the_ops_applied_in_turn(ops):
    orientation = ImageOrientation()

    _apply(orientation, ops)

    assert orientation.map_point(POINT, SIZE) == _display_ops_applied(ops, POINT, SIZE)
    assert orientation.unmap_point(orientation.map_point(POINT, SIZE), SIZE) == [
        *map(float, POINT)
    ]


def test_four_turns_and_double_flips_are_identity():
    orientation = ImageOrientation()

    _apply(orientation, ["rotate"] * 4 + ["flip_h", "flip_h", "flip_v", "flip_v"])

    assert orientation.trait_get(
        "quarter_turns", "flip_horizontal", "flip_vertical"
    ) == {"quarter_turns": 0, "flip_horizontal": False, "flip_vertical": False}


def test_quarter_turn_swaps_the_displayed_size():
    orientation = ImageOrientation()

    orientation.rotate_clockwise()

    assert orientation.oriented_size(SIZE) == (100, 200)
    assert orientation.map_point((0, 0), SIZE) == [100, 0]


# ------------------------------ Outline pane ------------------------------ #
@pytest.fixture
def pane():
    QApplication.instance() or QApplication([])

    image = QImage(*SIZE, QImage.Format_RGB32)
    image.fill(Qt.black)
    image.setPixelColor(*POINT, QColor(Qt.red))

    return OutlinePane(capture_frame=lambda: image)


#: Pane buttons per op name.
BUTTONS = {"rotate": "rotate", "flip_h": "flip_horizontal", "flip_v": "flip_vertical"}


@pytest.mark.parametrize(
    "ops",
    [["rotate"], ["flip_h"], ["flip_v"], ["rotate", "flip_h"], ["flip_v", "rotate"]],
)
def test_shown_frame_and_dots_follow_the_orientation(pane, ops):
    raw_quad = [[20.0, 10.0], [150.0, 15.0], [160.0, 80.0], [25.0, 90.0]]
    pane._overlay.set_quad(raw_quad)

    for op in ops:
        setattr(pane, BUTTONS[op], True)

    # The red raw pixel shows where the orientation maps its centre.
    x, y = pane.orientation.map_point((POINT[0] + 0.5, POINT[1] + 0.5), SIZE)
    shown = pane.canvas._pixmap_item.pixmap().toImage()
    assert shown.size().toTuple() == pane.orientation.oriented_size(SIZE)
    assert shown.pixelColor(int(x), int(y)) == QColor(Qt.red)

    # The dots moved with the image, and save reports raw pixels.
    assert pane._overlay.quad() != raw_quad

    accepted = []
    pane.observe(lambda event: accepted.append(event.new), "quad_accepted")
    pane.save = True

    assert [[round(c, 6) for c in point] for point in accepted[0]] == raw_quad

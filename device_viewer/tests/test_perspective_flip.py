# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PerspectiveModel.flip_output / rotate_output: both move the scene-side
quad about its centroid, so the camera transformation follows."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import QPointF

# Microdrop package imports.
from device_viewer.models.perspective import PerspectiveModel

#: Camera-pixel quad, clockwise from top-left.
CAMERA_QUAD = [(0, 0), (100, 0), (100, 50), (0, 50)]

#: Scene quad, clockwise from top-left; centroid (25, 40).
SCENE_QUAD = [(10, 20), (40, 20), (40, 60), (10, 60)]


def _points(coords):
    return [QPointF(x, y) for x, y in coords]


def _coords(points):
    return [(round(p.x(), 6), round(p.y(), 6)) for p in points]


@pytest.fixture
def model():
    return PerspectiveModel(
        reference_rect=_points(CAMERA_QUAD),
        transformed_reference_rect=_points(SCENE_QUAD),
    )


def test_horizontal_flip_mirrors_x_about_centre(model):
    model.flip_output(horizontal=True)

    assert _coords(model.transformed_reference_rect) == [
        (40, 20),
        (10, 20),
        (10, 60),
        (40, 60),
    ]


def test_vertical_flip_mirrors_y_about_centre(model):
    model.flip_output(horizontal=False)

    assert _coords(model.transformed_reference_rect) == [
        (10, 60),
        (40, 60),
        (40, 20),
        (10, 20),
    ]


@pytest.mark.parametrize("horizontal", [True, False])
def test_flipping_twice_restores_the_quad(model, horizontal):
    model.flip_output(horizontal)
    model.flip_output(horizontal)

    assert _coords(model.transformed_reference_rect) == SCENE_QUAD


def test_flip_starts_from_default_rect_when_none_placed():
    model = PerspectiveModel(default_rect=_points(SCENE_QUAD))

    model.flip_output(horizontal=True)

    assert _coords(model.transformed_reference_rect) == [
        (40, 20),
        (10, 20),
        (10, 60),
        (40, 60),
    ]
    assert model.perspective_transformation_possible()


def test_horizontal_flip_maps_camera_left_edge_to_scene_right_edge(model):
    model.flip_output(horizontal=True)

    top_left = model.transformation.map(QPointF(0, 0))
    bottom_left = model.transformation.map(QPointF(0, 50))
    top_right = model.transformation.map(QPointF(100, 0))

    assert _coords([top_left, bottom_left, top_right]) == [
        (40, 20),
        (40, 60),
        (10, 20),
    ]


def test_flip_then_rotate_composes(model):
    model.flip_output(horizontal=True)
    model.rotate_output(90)

    # Mirror x about 25, then rotate +90 (y down) about (25, 40):
    # (x, y) -> (25 - (y - 40), 40 + (x' - 25)).
    assert _coords(model.transformed_reference_rect) == [
        (45, 55),
        (45, 25),
        (5, 25),
        (5, 55),
    ]


def test_rotate_four_quarter_turns_restores_the_quad(model):
    for _ in range(4):
        model.rotate_output(90)

    assert _coords(model.transformed_reference_rect) == SCENE_QUAD

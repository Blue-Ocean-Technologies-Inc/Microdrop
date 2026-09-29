# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the canonical ROI geometry helpers."""

# Third-party imports.
import numpy as np

# Microdrop package imports.
from image_viewer.analysis.roi_geometry import (
    box_polygon,
    capsule_polygon,
    centre_of,
    normalize,
    outline_of,
    translated,
)


def test_normalize_upgrades_a_legacy_circle():
    kind, geometry = normalize("circle", [10.0, 20.0, 5.0])
    assert kind == "ellipse"
    assert geometry == [10.0, 20.0, 5.0, 5.0, 0.0]


def test_normalize_upgrades_a_legacy_box():
    # Pre-rotation (4 values) and pre-rounding (5) boxes both land on
    # the canonical six, square-cornered and unrotated.
    kind, geometry = normalize("box", [1.0, 2.0, 30.0, 40.0])
    assert kind == "box"
    assert geometry == [1.0, 2.0, 30.0, 40.0, 0.0, 0.0]
    assert normalize("box", [1.0, 2.0, 30.0, 40.0, 15.0])[1] == [
        1.0,
        2.0,
        30.0,
        40.0,
        15.0,
        0.0,
    ]


def test_normalize_clamps_a_corner_radius_to_the_shorter_side():
    assert normalize("box", [0.0, 0.0, 40.0, 20.0, 0.0, 99.0])[1][5] == 10.0
    assert normalize("box", [0.0, 0.0, 40.0, 20.0, 0.0, -5.0])[1][5] == 0.0


def test_normalize_is_idempotent():
    once = normalize("circle", [10.0, 20.0, 5.0])
    assert normalize(*once) == once


def test_centre_of_box_is_its_middle():
    assert centre_of("box", [0.0, 0.0, 10.0, 20.0, 0.0]) == (5.0, 10.0)
    assert centre_of("ellipse", [3.0, 4.0, 1.0, 1.0, 0.0]) == (3.0, 4.0)


def test_box_polygon_rotates_clockwise_in_image_coordinates():
    # y grows downward, so +90 degrees carries +x onto +y.
    polygon = box_polygon([0.0, 0.0, 10.0, 0.0, 90.0])
    corners = {(round(x, 6), round(y, 6)) for x, y in polygon}
    assert (5.0, -5.0) in corners
    assert (5.0, 5.0) in corners


def test_capsule_polygon_area_matches_the_analytic_value():
    half_length, radius = 20.0, 6.0
    polygon = capsule_polygon([50.0, 50.0, half_length, radius, 0.0], samples=256)
    x, y = polygon[:, 0], polygon[:, 1]
    # Shoelace formula over the closed outline.
    area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    expected = np.pi * radius**2 + 4.0 * radius * half_length
    assert abs(area - expected) / expected < 0.01


def test_capsule_polygon_rotation_moves_the_tip():
    flat = capsule_polygon([0.0, 0.0, 10.0, 2.0, 0.0], samples=64)
    turned = capsule_polygon([0.0, 0.0, 10.0, 2.0, 90.0], samples=64)
    assert flat[:, 0].max() > 11.0 and abs(flat[:, 1].max() - 2.0) < 0.01
    assert turned[:, 1].max() > 11.0 and abs(turned[:, 0].max() - 2.0) < 0.01


def test_normalize_passes_a_contour_through():
    kind, geometry = normalize("polygon", [0.0, 0.0, 10.0, 0.0, 0.0, 8.0])
    assert kind == "polygon"
    assert geometry == [0.0, 0.0, 10.0, 0.0, 0.0, 8.0]


def test_normalize_drops_a_contours_stray_value():
    _kind, geometry = normalize("polygon", [0.0, 0.0, 10.0, 0.0, 5.0])
    assert geometry == [0.0, 0.0, 10.0, 0.0]


def test_centre_of_contour_is_its_mean_vertex():
    centre = centre_of("polygon", [0.0, 0.0, 10.0, 0.0, 5.0, 9.0])
    assert centre == (5.0, 3.0)


def test_outline_of_answers_for_every_polygon_shaped_kind():
    box = outline_of("box", [0.0, 0.0, 10.0, 20.0, 0.0])
    capsule = outline_of("capsule", [0.0, 0.0, 10.0, 2.0, 0.0])
    contour = outline_of("polygon", [0.0, 0.0, 10.0, 0.0, 0.0, 8.0])
    assert box.shape == (4, 2)
    assert capsule.shape[1] == 2 and len(capsule) > 4
    assert contour.tolist() == [[0.0, 0.0], [10.0, 0.0], [0.0, 8.0]]


def test_outline_of_is_empty_below_the_minimum_vertices():
    assert len(outline_of("polygon", [0.0, 0.0, 10.0, 0.0])) == 0


def test_a_rounded_box_keeps_its_bounds_and_loses_its_corners():
    sharp = box_polygon([0.0, 0.0, 100.0, 60.0, 0.0, 0.0])
    rounded = box_polygon([0.0, 0.0, 100.0, 60.0, 0.0, 20.0])
    # Same extent — rounding cuts the corners, it does not shrink the
    # shape — but no vertex reaches a corner any more.
    assert rounded[:, 0].min() == 0.0 and rounded[:, 0].max() == 100.0
    assert rounded[:, 1].min() == 0.0 and rounded[:, 1].max() == 60.0
    assert len(rounded) > len(sharp)
    assert not any(x in (0.0, 100.0) and y in (0.0, 60.0) for x, y in rounded)


def test_a_rounded_box_still_rotates_about_its_centre():
    upright = box_polygon([0.0, 0.0, 40.0, 40.0, 0.0, 10.0])
    turned = box_polygon([0.0, 0.0, 40.0, 40.0, 90.0, 10.0])
    # A square rounded equally at every corner maps onto itself.
    assert np.allclose(
        sorted(map(tuple, np.round(upright, 6))),
        sorted(map(tuple, np.round(turned, 6))),
    )


def test_translated_moves_an_anchor_or_every_vertex():
    assert translated("box", [10.0, 20.0, 30.0, 40.0, 0.0, 5.0], 12.0, -3.0) == [
        22.0,
        17.0,
        30.0,
        40.0,
        0.0,
        5.0,
    ]
    assert translated("ellipse", [10.0, 20.0, 5.0, 5.0, 45.0], 1.0, 2.0) == [
        11.0,
        22.0,
        5.0,
        5.0,
        45.0,
    ]
    assert translated("polygon", [0.0, 0.0, 10.0, 0.0, 10.0, 10.0], 2.0, 3.0) == [
        2.0,
        3.0,
        12.0,
        3.0,
        12.0,
        13.0,
    ]

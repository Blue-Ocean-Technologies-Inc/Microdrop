"""SVG path flattening in SVGProcessor._parse_path_string.

Curved segments (arcs, Béziers) are sampled into polygon vertices so
circular electrodes/markers (Inkscape encodes a circle as two Arc
segments) yield real shapely geometry. Straight-command paths keep their
exact endpoint-only behavior.
"""
import numpy as np
import pytest
from shapely.geometry import Polygon

from device_viewer.utils.dmf_utils_helpers import (
    CURVE_SEGMENT_SAMPLES, SVGProcessor,
)

# A real Inkscape circle path (r = 2.238187) that previously parsed to three
# nearly-collinear points — a degenerate, zero-area polygon.
CIRCLE_D = ("m 519.5488,1056.6446 "
            "a 2.238187,2.238187 0 0 1 -4.38913,-0.6729 "
            "2.238187,2.238187 0 1 1 4.38913,0.6729")
CIRCLE_RADIUS = 2.238187


def test_circle_path_flattens_to_polygon():
    points = SVGProcessor._parse_path_string(CIRCLE_D)
    # 1 move endpoint + 2 sampled arcs
    assert len(points) == 1 + 2 * CURVE_SEGMENT_SAMPLES

    polygon = Polygon(points)
    expected_area = np.pi * CIRCLE_RADIUS ** 2
    assert polygon.is_valid
    assert polygon.area == pytest.approx(expected_area, rel=0.01)

    # Every vertex sits on the circle (measure from the shapely centroid,
    # which is unbiased by the arcs' unequal sampling density).
    center = np.array(polygon.centroid.coords[0])
    radii = np.linalg.norm(points - center, axis=1)
    assert radii == pytest.approx(CIRCLE_RADIUS, rel=0.01)


def test_straight_command_paths_keep_endpoint_behavior():
    points = SVGProcessor._parse_path_string("M 0,0 H 10 V 5 H 0 Z")
    assert len(points) == 5                     # M + H + V + H + Z endpoints
    assert Polygon(points).area == 50.0


def test_bezier_segments_are_sampled():
    points = SVGProcessor._parse_path_string("M 0,0 C 0,10 10,10 10,0 Z")
    assert len(points) == 1 + CURVE_SEGMENT_SAMPLES + 1
    assert Polygon(points).area > 0

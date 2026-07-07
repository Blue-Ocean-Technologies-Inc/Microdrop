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

# A notched electrode mixing arcs with h/v runs (real Inkscape output). Its
# final arc lands on the FIRST arc's endpoint rather than the path start, so
# the raw flattened ring self-intersects near the seam — SVG's fill rule
# tolerates that; shapely needs the buffer(0) repair applied in
# SvgUtil.get_electrode_polygons.
NOTCHED_D = ("m 484.35753,1040.403 "
             "a 2.427163,2.427163 0 0 0 1.86089,1.7124 "
             "v 1.3988 h -1.72913 -1.95591 v -2.0944 h -1.51181 "
             "v -3.4898 h 1.51181 v -1.9749 h 3.68504 v 1.3988 "
             "a 2.427163,2.427163 0 0 0 0,4.7615")


def test_mixed_arc_and_straight_path_flattens():
    from svg.path import parse_path, Arc

    points = SVGProcessor._parse_path_string(NOTCHED_D)
    segments = list(parse_path(NOTCHED_D))
    arcs = [s for s in segments if isinstance(s, Arc)]
    straights = [s for s in segments if not isinstance(s, Arc)]
    assert len(arcs) == 2 and len(straights) == 11
    assert len(points) == len(straights) + len(arcs) * CURVE_SEGMENT_SAMPLES

    # Straight endpoints are preserved verbatim among the vertices.
    for segment in straights:
        end = (segment.end.real, segment.end.imag)
        assert any(np.allclose(p, end) for p in points)

    # Every sampled arc vertex lies on its arc's own circle (svg.path
    # exposes the analytic center/radius — no magic numbers needed).
    for arc in arcs:
        center = np.array([arc.center.real, arc.center.imag])
        for i in range(1, CURVE_SEGMENT_SAMPLES + 1):
            p = arc.point(i / CURVE_SEGMENT_SAMPLES)
            radius = np.linalg.norm(np.array([p.real, p.imag]) - center)
            assert radius == pytest.approx(arc.radius.real, rel=1e-6)


def test_self_intersecting_ring_is_repaired():
    from device_viewer.utils.dmf_utils_helpers import as_valid_polygon

    points = SVGProcessor._parse_path_string(NOTCHED_D)
    raw = Polygon(points)
    assert not raw.is_valid            # overlapping arc traversals at the seam

    repaired = as_valid_polygon(raw)   # what get_electrode_polygons applies
    assert repaired.geom_type == "Polygon"
    assert repaired.is_valid
    assert repaired.area == pytest.approx(26.17, rel=0.01)


def test_multi_lobe_repair_keeps_largest_lobe():
    from device_viewer.utils.dmf_utils_helpers import as_valid_polygon

    # A ring pinched at the origin: buffer(0) splits it into two lobes
    # (areas 1 and 4); real device SVGs produce such shapes and the
    # SvgUtil.polygons trait requires a single Polygon per electrode.
    pinched = Polygon([(0, 0), (1, 0), (1, 1), (0, 1),
                       (0, 0), (-2, 0), (-2, -2), (0, -2)])
    assert pinched.buffer(0).geom_type == "MultiPolygon"

    repaired = as_valid_polygon(pinched)
    assert repaired.geom_type == "Polygon"
    assert repaired.is_valid
    assert repaired.area == 4.0        # dominant lobe wins


def test_valid_polygon_passes_through_untouched():
    from device_viewer.utils.dmf_utils_helpers import as_valid_polygon

    square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    assert as_valid_polygon(square) is square

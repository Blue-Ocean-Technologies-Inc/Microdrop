"""Tests for label_geometry — the channel-label anchor/extent for a shape.

Pure geometry (no QApplication needed): the pole-of-inaccessibility anchor
must sit inside curved/concave electrodes where the bbox center falls
outside, while plain rectangles keep the exact legacy anchor and font
extent so standard devices render pixel-identically.
"""
import numpy as np
from shapely.geometry import Point, Polygon

from device_viewer.utils.dmf_utils_helpers import SVGProcessor, as_valid_polygon
from device_viewer.views.electrode_view.electrode_view_helpers import label_geometry


def test_rectangle_keeps_legacy_center_and_extent():
    anchor_x, anchor_y, extent = label_geometry(
        np.array([(0, 0), (10, 0), (10, 5), (0, 5)], dtype=float))
    # bbox center and min side — the old _fit_text_in_path values verbatim,
    # even though the pole of inaccessibility ties all along the center line
    assert (anchor_x, anchor_y, extent) == (5.0, 2.5, 5.0)


def test_l_shape_anchor_moves_inside():
    l_shape = np.array([(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)],
                       dtype=float)
    polygon = Polygon(l_shape)
    assert not polygon.contains(Point(5, 5))     # bbox center is in the notch

    anchor_x, anchor_y, extent = label_geometry(l_shape)
    assert polygon.contains(Point(anchor_x, anchor_y))
    # extent is the inscribed diameter around the anchor, so a square of
    # that clearance fits fully inside the shape
    assert 0 < extent <= 4 * 2


# The real notched Inkscape electrode from test_dmf_path_parsing.
NOTCHED_D = ("m 484.35753,1040.403 "
             "a 2.427163,2.427163 0 0 0 1.86089,1.7124 "
             "v 1.3988 h -1.72913 -1.95591 v -2.0944 h -1.51181 "
             "v -3.4898 h 1.51181 v -1.9749 h 3.68504 v 1.3988 "
             "a 2.427163,2.427163 0 0 0 0,4.7615")


def test_curved_electrode_anchor_inside_with_room():
    points = np.array(SVGProcessor._parse_path_string(NOTCHED_D))
    repaired = as_valid_polygon(Polygon(points))
    coords = np.array(repaired.exterior.coords)

    anchor_x, anchor_y, extent = label_geometry(coords)
    assert repaired.contains(Point(anchor_x, anchor_y))
    assert extent == 2 * repaired.exterior.distance(Point(anchor_x, anchor_y))
    assert extent > 0


def test_degenerate_ring_falls_back_to_bbox():
    collinear = np.array([(0, 0), (5, 0), (10, 0)], dtype=float)
    anchor_x, anchor_y, extent = label_geometry(collinear)
    assert (anchor_x, anchor_y) == (5.0, 0.0)    # bbox center
    assert extent == 0.0                          # no room — degenerate

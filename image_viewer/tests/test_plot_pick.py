# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Picking the plot point a click landed on, in display coordinates."""

# Standard library imports.
import math

# Microdrop package imports.
from image_viewer.analysis.consts import PLOT_CLICK_SLOP_PX, PLOT_PICK_RADIUS_PX
from image_viewer.analysis.plot_pick import left_press_point, nearest_point

POINTS = [("a.png", 100.0, 100.0), ("b.png", 110.0, 100.0), ("c.png", 300.0, 50.0)]


def test_the_nearest_point_within_the_radius_is_picked():
    assert nearest_point(POINTS, (104.0, 101.0), PLOT_PICK_RADIUS_PX) == "a.png"
    assert nearest_point(POINTS, (107.0, 99.0), PLOT_PICK_RADIUS_PX) == "b.png"


def test_a_click_beyond_the_radius_picks_nothing():
    assert nearest_point(POINTS, (200.0, 100.0), PLOT_PICK_RADIUS_PX) is None
    assert nearest_point(POINTS, (300.0, 50.0 + 8.5), PLOT_PICK_RADIUS_PX) is None


def test_the_radius_itself_is_still_a_hit():
    assert nearest_point(POINTS, (300.0, 58.0), PLOT_PICK_RADIUS_PX) == "c.png"


def test_gaps_and_unplottable_points_are_never_picked():
    points = [
        ("gap.png", 100.0, math.nan),
        ("no-step.png", math.nan, 100.0),
        ("log-hidden.png", -math.inf, 100.0),
        ("far.png", 106.0, 100.0),
    ]

    assert nearest_point(points, (100.0, 100.0), PLOT_PICK_RADIUS_PX) == "far.png"


def test_nothing_to_pick_from_picks_nothing():
    assert nearest_point([], (0.0, 0.0), PLOT_PICK_RADIUS_PX) is None


def test_jitter_within_the_slop_is_still_a_click():
    press = (100.0, 100.0)

    assert not left_press_point(press, (100.0, 100.0), PLOT_CLICK_SLOP_PX)
    assert not left_press_point(press, (102.0, 101.0), PLOT_CLICK_SLOP_PX)
    assert not left_press_point(press, (103.0, 100.0), PLOT_CLICK_SLOP_PX)


def test_leaving_the_slop_starts_a_pan():
    assert left_press_point((100.0, 100.0), (103.0, 102.0), PLOT_CLICK_SLOP_PX)
    assert left_press_point((100.0, 100.0), (90.0, 100.0), PLOT_CLICK_SLOP_PX)

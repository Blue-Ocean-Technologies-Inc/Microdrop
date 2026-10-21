# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Clicks on the ROI plot, in display coordinates: whether a press
drifted far enough to be a pan, and which point a click landed on.
Pure functions, so the canvas's click handling is testable without
one."""

# Standard library imports.
import math


def nearest_point(points, target, radius):
    """The key of the point nearest ``target`` within ``radius``, or None
    when none lies that close.

    Parameters
    ----------
    points : iterable of (key, x, y)
        Candidate points in display pixels. One with a non-finite
        coordinate — a gap, an image the axis has no x for — is never
        picked.
    target : (x, y)
        Where the click landed, in display pixels.
    radius : float
        How far from ``target`` a point may lie and still be picked.
    """
    nearest, nearest_distance = None, math.inf

    for key, x, y in points:
        distance = math.hypot(x - target[0], y - target[1])

        # NaN fails both comparisons, so a gap falls out here too.
        if distance <= radius and distance < nearest_distance:
            nearest, nearest_distance = key, distance

    return nearest


def left_press_point(press, position, slop):
    """Whether ``position`` lies more than ``slop`` from ``press``, both
    (x, y) in display pixels — where a press stops being a click and
    becomes a pan."""
    return math.hypot(position[0] - press[0], position[1] - press[1]) > slop

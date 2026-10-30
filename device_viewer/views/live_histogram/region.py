# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Live Histogram's region of interest, Qt-free: the rectangle maths
on frame fractions (left, top, right, bottom), and the region picker's
model, which turns presses and drags into region edits.

A drag takes hold of some of the region's sides — indices 0 left, 1 top,
2 right, 3 bottom — and moves them by the pointer's travel: one side for
an edge, two for a corner, all four (a move) inside the region, and the
right and bottom sides of a fresh region pinned at the press outside it.
"""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Float,
    HasTraits,
    Int,
    Property,
    Str,
    Tuple,
)

# Local imports.
from ...consts import (
    LIVE_HISTOGRAM_FULL_FRAME_REGION,
    LIVE_HISTOGRAM_REGION_MIN_FRACTION,
)

#: Every side of the region: a drag inside it moves the whole region.
ALL_SIDES = (0, 1, 2, 3)

#: The sides a fresh region's drag pulls, away from its pinned corner.
NEW_REGION_SIDES = (2, 3)


def is_full_frame(region):
    """True when ``region`` covers the whole frame."""
    return tuple(region) == LIVE_HISTOGRAM_FULL_FRAME_REGION


def _clamped_span(start, end, min_fraction):
    """The (low, high) of one axis, sorted, inside [0, 1], and at least
    ``min_fraction`` long."""
    low, high = sorted(min(max(float(value), 0.0), 1.0) for value in (start, end))

    if high - low < min_fraction:
        centre = (low + high) / 2
        low = min(max(centre - min_fraction / 2, 0.0), 1.0 - min_fraction)
        high = low + min_fraction

    return low, high


def clamp_region(region, min_fraction=LIVE_HISTOGRAM_REGION_MIN_FRACTION):
    """``region`` with its sides in order, inside the frame, and no side
    shorter than ``min_fraction`` of it."""
    left, right = _clamped_span(region[0], region[2], min_fraction)
    top, bottom = _clamped_span(region[1], region[3], min_fraction)

    return (left, top, right, bottom)


def region_in_pixels(region, frame_size):
    """(left, top, width, height) of ``region`` in the pixels of a frame of
    ``frame_size`` (width, height); never less than one pixel a side."""
    frame_width, frame_height = frame_size
    left, top, right, bottom = region

    left_px = min(round(left * frame_width), frame_width - 1)
    top_px = min(round(top * frame_height), frame_height - 1)
    right_px = max(round(right * frame_width), left_px + 1)
    bottom_px = max(round(bottom * frame_height), top_px + 1)

    return left_px, top_px, right_px - left_px, bottom_px - top_px


def format_region(region, frame_size):
    """The region readout: its size and offset in camera pixels, or its
    share of the frame while the frame size is unknown."""

    if is_full_frame(region):
        return "Full frame"

    if min(frame_size) <= 0:
        left, top, right, bottom = region

        return f"{(right - left) * 100:.0f} × {(bottom - top) * 100:.0f} % of the frame"

    left, top, width, height = region_in_pixels(region, frame_size)

    return f"{width} × {height} px at ({left}, {top})"


def grabbed_sides(region, point, tolerance):
    """The sides of ``region`` a press at ``point`` takes hold of.

    Parameters
    ----------
    region : tuple of float
        (left, top, right, bottom), in frame fractions.
    point : tuple of float
        (x, y) of the press, in frame fractions.
    tolerance : tuple of float
        (x, y) distance, in frame fractions, within which a press grabs a
        side.

    Returns
    -------
    tuple of int
        The grabbed side indices: one for an edge, two for a corner,
        ``ALL_SIDES`` inside the region, and none outside it (or inside a
        full-frame region, which cannot move): a fresh region.
    """
    left, top, right, bottom = region
    x, y = point
    x_tolerance, y_tolerance = tolerance

    within_rows = top - y_tolerance <= y <= bottom + y_tolerance
    within_columns = left - x_tolerance <= x <= right + x_tolerance
    sides = []

    # On a region narrower than two grab zones, the nearer side wins.
    if within_rows:
        horizontal = min(((abs(x - left), 0), (abs(x - right), 2)))

        if horizontal[0] <= x_tolerance:
            sides.append(horizontal[1])

    if within_columns:
        vertical = min(((abs(y - top), 1), (abs(y - bottom), 3)))

        if vertical[0] <= y_tolerance:
            sides.append(vertical[1])

    if sides:
        return tuple(sorted(sides))

    inside = left < x < right and top < y < bottom

    if inside and not is_full_frame(region):
        return ALL_SIDES

    return ()


def dragged_region(anchor_region, sides, start, point):
    """The region after a drag from ``start`` to ``point`` (frame
    fractions) holding ``sides`` of ``anchor_region``: a move keeps its
    size and stops at the frame's edges; a resize may cross over, swapping
    the sides it pulls past."""
    dx = point[0] - start[0]
    dy = point[1] - start[1]
    left, top, right, bottom = anchor_region

    if tuple(sides) == ALL_SIDES:
        dx = min(max(dx, -left), 1.0 - right)
        dy = min(max(dy, -top), 1.0 - bottom)

        return (left + dx, top + dy, right + dx, bottom + dy)

    region = list(anchor_region)

    for side in sides:
        region[side] += dx if side in (0, 2) else dy

    return clamp_region(region)


class RegionPickerModel(HasTraits):
    """The region picker's state: the region being edited and the drag in
    progress. The canvas reports presses here in frame fractions; the
    dialog's controller handles the frame (fit, recapture)."""

    #: The edited region, frame fractions (left, top, right, bottom).
    region = Tuple(Float(0.0), Float(0.0), Float(1.0), Float(1.0))

    #: (width, height) of the captured frame, in camera pixels.
    frame_size = Tuple(Int(), Int())

    #: The region readout.
    region_text = Property(Str, observe="region, frame_size")

    #: Refit the frame in the view.
    fit = Button()

    #: Capture a fresh frame from the camera.
    recapture = Button()

    #: Cover the whole frame again.
    full_frame = Button()

    #: Apply the region to the histogram as it is edited, not only on OK.
    live = Bool(False)

    #: The sides the current drag holds (none between drags), and where it
    #: started (frame fractions) on which region.
    _drag_sides = Tuple()
    _drag_start = Tuple(Float(), Float())
    _drag_anchor = Tuple(Float(), Float(), Float(), Float())

    def begin_drag(self, point, tolerance):
        """Take hold of what lies under a press at ``point``; outside the
        region, pin a fresh region's corner there."""
        sides = grabbed_sides(self.region, point, tolerance)

        if sides:
            anchor = self.region
        else:
            sides = NEW_REGION_SIDES
            anchor = (point[0], point[1], point[0], point[1])

        self.trait_set(_drag_sides=sides, _drag_start=tuple(point), _drag_anchor=anchor)

    def drag_to(self, point):
        """Follow the pointer to ``point``. A fresh region appears only
        once the drag reaches the minimum region size."""

        if not self._drag_sides:
            return

        dx = abs(point[0] - self._drag_start[0])
        dy = abs(point[1] - self._drag_start[1])
        is_fresh = self._drag_anchor[:2] == self._drag_anchor[2:]

        if is_fresh and max(dx, dy) < LIVE_HISTOGRAM_REGION_MIN_FRACTION:
            return

        self.region = dragged_region(
            self._drag_anchor, self._drag_sides, self._drag_start, point
        )

    def end_drag(self):
        self._drag_sides = ()

    def _full_frame_fired(self):
        self.region = LIVE_HISTOGRAM_FULL_FRAME_REGION

    # ------------------------------------------------------------------ #
    # Property getters                                                     #
    # ------------------------------------------------------------------ #
    def _get_region_text(self):
        return format_region(self.region, self.frame_size)

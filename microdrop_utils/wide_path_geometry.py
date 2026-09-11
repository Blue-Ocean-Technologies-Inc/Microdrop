# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure geometry for wide paths: no traits, no Qt.

A *wide path* is a route — a chain of neighbouring electrode ids, revisits
allowed — plus a slug shape: ``left``/``right`` extra lanes across the
direction of travel and the usual ``trail_length``/``trail_overlay`` along
it. Execution only ever asks one question, *which electrodes are on at each
phase*, and :func:`slug_phases` answers it with the rules settled in the
corner-turning game (2026-09-09 to 2026-09-11; the picks are the test suite).

The module is laid out as a pipeline, top to bottom:

1. **Lattice** — pitch, headings, snapping a point to an electrode.
2. **Route** — headings along it, loops and their unrolling.
3. **Lanes** — which side of the route each lane count goes to.
4. **Blocks** — the electrodes one W x T block covers from an anchor point.
5. **Positions** — where the block sits at each phase: one schedule for a
   block that re-hangs at corners, one for a block that only translates.
6. **Phases** — clipping, the ramps, and ``slug_phases`` tying it together.

======================  ==========================================================
shape                   rule
======================  ==========================================================
width 1                 the trail is the route itself — the shipped trail
                        algorithm, bent corners included
route shorter than      hold: every electrode the slug would cover comes on
the trail               as one phase and stays on
width == trail          a square never notices a corner: a rigid footprint
                        that only translates — hung behind its head along
                        the way it travels, centred across it, sliding on to
                        centre on a corner electrode before it turns
rotation lock           the same for any shape: the block keeps the
                        orientation it started with, so a ``3x2 r`` reads
                        ``2x3 u`` after the turn
anything else           a W x T block hung behind the head along the heading
                        it arrives by, re-hung at every turn (a one-step jog
                        included); with no trail the corner electrode shows
                        both orientations — its arriving row, then its
                        departing row — before the slug moves on
loop                    a route whose first electrode is repeated last (the
                        device viewer's definition) plays its cycle
                        ``repetitions`` times and then returns onto the
                        start electrode, so the slug ends where it began;
                        the whole run is one unrolled route, striding
                        straight through the seams
======================  ==========================================================

Vocabulary used throughout:

- **centroids** — ``id -> (x, y)`` in SVG coordinates (y grows downward).
- **neighbours** — ``id -> [ids]``, the device's adjacency graph.
- **pitch** — the lattice spacing, so "one lane over" means the same on any
  device; measured as the median neighbour distance.
- **heading** — a unit vector for the direction of travel. The heading *at*
  a route electrode is the direction the route arrives by; the first
  electrode takes the direction it leaves by.
- **head** — the route electrode a phase belongs to; the block's **anchor**
  is the point its leading cell sits on.
- **lane** — signed offset across the heading: positive to the screen-left
  of travel, negative to the screen-right, 0 on the route.
- **lane frame** — how the two lane counts are read. ``LEFT_RIGHT``: as
  screen-left / screen-right of travel. ``IN_OUT``: as inside / outside of
  the turn, so lanes can hug the outer rung of a track whichever way it
  bends (see :func:`outer_sides` and :func:`lane_counts`).
- **along / across leg** — for a translating block, a leg parallel to the
  heading it started with, or perpendicular to it.

Phases are simply numbered by their place in the list, as the shipped
executor numbers them. Each carries the route index it belongs to and the
direction of travel there, which is what the notation prints beside the
number.

Electrodes that do not exist — beyond the device edge, inside a reservoir
neck — are left out of a block; nothing is faked in their place. Instead the
**actuation count stays constant**: a clipped block is topped up with the
previous phase's cells nearest the head (:func:`keep_count`). The count only
comes down at the end of the route, and only with **soft end** on; **soft
start** brings it up the same way, a row at a time (:func:`ramp_down`,
:func:`ramp_up`).
"""

# Standard library imports.
import math
import statistics
from collections import namedtuple

# Microdrop utils imports.
from microdrop_utils.route_execution import PathExecutionService

#: How far (in pitches) a snapped lattice position may be from the nearest
#: electrode centroid and still count as that electrode. Half a pitch: any
#: further and the position is between electrodes, i.e. a hole.
SNAP_TOLERANCE = 0.5

#: Lane frames: the two lane counts read as screen-left / screen-right of
#: travel, or as inside / outside of the turn.
LEFT_RIGHT, IN_OUT = "left/right", "in/out"

#: One phase: the route index it belongs to (``head``), the direction of
#: travel there (``heading``), and the electrodes on (``ids``).
Phase = namedtuple("Phase", "head heading ids")

#: One block placement: the route index it belongs to, the ``anchor`` point
#: its leading cell sits on, the ``heading`` it hangs behind that point
#: along, and its ``(left, right)`` lane counts across that heading.
Position = namedtuple("Position", "head anchor heading lanes")


# ------------------------------------------------------------------ lattice
def lattice_pitch(centroids, neighbours):
    """The lattice spacing: the median centroid distance between
    neighbouring electrodes.

    The median, not the mean, so a device's few oversized reservoir
    electrodes cannot skew it. Falls back to 1.0 with no neighbours at all.
    """
    distances = [
        math.dist(centroids[a], centroids[b])
        for a, adjacent in neighbours.items()
        for b in adjacent
        if a in centroids and b in centroids
    ]

    return statistics.median(distances) if distances else 1.0


def unit(dx, dy):
    """``(dx, dy)`` scaled to length 1; ``(0, 0)`` stays ``(0, 0)``."""
    length = math.hypot(dx, dy)

    return (dx / length, dy / length) if length else (0.0, 0.0)


def left_normal(heading):
    """The unit vector to the screen-left of ``heading``.

    SVG y grows downward, so travelling right ``(1, 0)`` has screen-left
    ``(0, -1)`` — up. This is the one place that convention is encoded;
    every lane offset goes through it.
    """
    return (heading[1], -heading[0])


def axis(heading):
    """``heading`` rounded onto the lattice axes, so two headings compare
    equal when a real device's slightly-off centroids make them differ."""
    return (round(heading[0]), round(heading[1]))


def nearest_electrode(point, centroids, pitch):
    """The id of the electrode whose centroid is nearest ``point``, or None
    when none lies within ``SNAP_TOLERANCE`` pitches — a hole."""
    best, best_distance = None, SNAP_TOLERANCE * pitch

    for electrode_id, centroid in centroids.items():
        distance = math.dist(point, centroid)

        if distance < best_distance:
            best, best_distance = electrode_id, distance

    return best


# -------------------------------------------------------------------- route
def route_headings(route, centroids, cycle_length=0):
    """One unit heading per route electrode: the direction the route
    arrives by, except the first electrode, which takes the direction it
    leaves by (a lone electrode is given "right").

    ``cycle_length`` marks an unrolled loop (see :func:`unroll`): its first
    electrode is then arrived at too, by the cycle's last electrode.
    """
    points = [centroids[electrode_id] for electrode_id in route]

    if len(points) == 1:
        return [(1.0, 0.0)]

    headings = []

    for index in range(len(points)):
        previous = points[0] if index == 0 else points[index - 1]
        current = points[1] if index == 0 else points[index]
        headings.append(unit(current[0] - previous[0], current[1] - previous[1]))

    if cycle_length and len(points) > cycle_length:
        headings[0] = headings[cycle_length]

    return headings


def leaving_heading(headings):
    """The heading of the route's first leg — what a translating block is
    aligned with. The first electrode's own heading is the arriving one on
    a loop, so the second electrode's is read instead."""
    return headings[min(1, len(headings) - 1)]


def turns_at(index, headings):
    """Whether the route changes direction at ``index``, i.e. between the
    heading it arrives by and the one it leaves by."""
    if index + 1 >= len(headings):
        return False

    return axis(headings[index]) != axis(headings[index + 1])


def is_loop(route):
    """A closed route as the device viewer defines it: the first electrode
    repeated last."""
    return len(route) >= 2 and route[0] == route[-1]


def unroll(route, repetitions, trail_length):
    """The route a loop actually plays: its cycle ``repetitions`` times and
    then far enough onto the next lap for the block to sit at its first
    position again — the shipped return phase, so the slug ends where it
    began. An open route is returned as it is."""
    if not is_loop(route):
        return list(route)

    cycle = route[:-1]

    return cycle * repetitions + cycle[:trail_length]


def merged(route, other):
    """The two routes joined at their shared endpoint — the device viewer's
    merge: ``other`` continues ``route`` when it starts where ``route``
    ends, or precedes it when it ends where ``route`` starts. None when
    they share no endpoint."""
    if route and other and route[-1] == other[0]:
        return list(route) + list(other[1:])

    if route and other and other[-1] == route[0]:
        return list(other[:-1]) + list(route)

    return None


# -------------------------------------------------------------------- lanes
def outer_sides(route, centroids, headings=None):
    """Which screen side is the *outside* at each route electrode: +1 for
    screen-left, -1 for screen-right.

    At a corner the outside is the convex side, opposite the turn. A
    straight electrode takes the corner nearest ahead of it (the whole leg
    agrees with the turn it approaches), or the last corner behind it once
    there is none ahead. With no corner at all every electrode is -1, so
    in / out regresses to left / right.
    """
    headings = headings or route_headings(route, centroids)

    # The outside of each corner, keyed by the corner's route index.
    outside_at_corner = {}

    for index in range(len(route) - 1):
        if not turns_at(index, headings):
            continue

        arriving, departing = headings[index], headings[index + 1]
        cross = arriving[0] * departing[1] - arriving[1] * departing[0]
        # SVG y grows downward: a positive cross is a turn to the screen-
        # right, whose outside is the screen-left.
        outside_at_corner[index] = 1 if cross > 0 else -1

    # Walk the route: the corner that *governs* an electrode — decides its
    # outside — is the nearest one still ahead; once the last corner is
    # behind, that last corner keeps governing to the end of the route.
    sides = []
    governing = None

    for index in range(len(route)):
        ahead = next(
            (
                side
                for corner, side in sorted(outside_at_corner.items())
                if corner >= index
            ),
            None,
        )
        governing = ahead if ahead is not None else governing
        sides.append(governing if governing is not None else -1)

    return sides


def lane_counts(headings, sides, left, right, lane_frame, translating):
    """``(left, right)`` lane counts per route electrode.

    In the left / right frame the counts are what the user typed. In the
    in / out frame ``left`` is the inside count and ``right`` the outside
    count, placed so the outside count lands on the outer side (``sides``,
    from :func:`outer_sides`):

    - a re-hung block reads its lanes across the heading it arrives by, so
      each electrode simply swaps the counts when its outside is to the
      screen-left;
    - a translating block reads them across the heading it started with,
      so they mirror to whichever side of that axis the outside lies on.
      An across leg has no side to choose and keeps the last one — or takes
      the first one decided, when a loop opens on a corner.
    """
    if lane_frame == LEFT_RIGHT:
        return [(left, right)] * len(headings)

    inside, outside = left, right

    def counts(sign):
        return (outside, inside) if sign > 0 else (inside, outside)

    if not translating:
        return [counts(side) for side in sides]

    ax, ay = left_normal(leaving_heading(headings))
    decided = []

    for heading, side in zip(headings, sides):
        nx, ny = left_normal(heading)
        dot = side * (nx * ax + ny * ay)
        decided.append((1 if dot > 0 else -1) if abs(dot) > 0.5 else None)

    sign = next((s for s in decided if s is not None), -1)
    lanes = []

    for choice in decided:
        sign = choice if choice is not None else sign
        lanes.append(counts(sign))

    return lanes


# ------------------------------------------------------------------- blocks
def block_cells(anchor, heading, left, right, trail_length, centroids, pitch):
    """The electrode ids of one W x T block whose leading cell sits on
    ``anchor`` and which hangs behind it along ``heading``.

    The block is laid out in the anchor's frame — ``trail_length`` cells
    back along the heading, ``left`` and ``right`` lanes across it — and
    every position is snapped to the nearest electrode, so the same code
    serves a synthetic grid and a real device SVG; a position with nothing
    under it is dropped.
    """
    x, y = anchor
    nx, ny = left_normal(heading)
    ids = []

    for along in range(-(trail_length - 1), 1):
        for lane in range(-right, left + 1):
            point = (
                x + along * heading[0] * pitch + lane * nx * pitch,
                y + along * heading[1] * pitch + lane * ny * pitch,
            )
            electrode_id = nearest_electrode(point, centroids, pitch)

            if electrode_id is not None and electrode_id not in ids:
                ids.append(electrode_id)

    return ids


def block_footprint(head_id, heading, left, right, trail_length, centroids, pitch):
    """:func:`block_cells` with the route electrode ``head_id`` as the
    leading cell."""
    return block_cells(
        centroids[head_id], heading, left, right, trail_length, centroids, pitch
    )


# ---------------------------------------------------------------- positions
def stride_of(extent, overlay):
    """How many electrodes a block ``extent`` long advances per phase with
    ``overlay`` cells shared between consecutive phases — at least one."""
    return max(extent - min(overlay, extent - 1), 1)


def run_points(start, finish, stride, pitch):
    """The anchor points of a straight run from ``start`` to ``finish``,
    every ``stride`` pitches and always ending on ``finish``: ``[(k, point)]``
    with ``k`` the pitches travelled, plus the run's total in pitches.
    Empty when the two points coincide."""
    dx, dy = finish[0] - start[0], finish[1] - start[1]
    length = math.hypot(dx, dy)
    steps = round(length / pitch)

    if not steps:
        return [], 0

    ux, uy = dx / length, dy / length
    points = [
        (k, (start[0] + k * ux * pitch, start[1] + k * uy * pitch))
        for k in [*range(stride, steps, stride), steps]
    ]

    return points, steps


def rehung_positions(route, headings, lanes, trail_length, trail_overlay, centroids):
    """Placements of a block that re-hangs behind its head at every turn.

    Heads start at ``T - 1`` (the block is complete once ``T`` electrodes
    lie behind its head), advance by the stride the shipped trail uses, and
    always finish on the last electrode; the stride ignores corners. Each
    block hangs behind its head along the heading the route arrives by. A
    bar (no trail) also shows the turn on the corner electrode itself: its
    departing row is an extra placement before the head moves on, and it
    takes the lanes of the leg it departs onto — the next electrode's — so
    the lane lands where the next phase will have it, not across the route
    from it (an S-bend with one outside lane would otherwise swing the lane
    from one side to the other in a single phase).
    """
    stride = stride_of(trail_length, trail_overlay)
    heads = list(range(trail_length - 1, len(route), stride))

    if heads[-1] != len(route) - 1:
        heads.append(len(route) - 1)

    positions = []

    for index in heads:
        anchor = centroids[route[index]]
        positions.append(Position(index, anchor, headings[index], lanes[index]))

        if trail_length == 1 and turns_at(index, headings):
            positions.append(
                Position(index, anchor, headings[index + 1], lanes[index + 1])
            )

    return positions


def translating_positions(
    route, headings, lanes, trail_length, trail_overlay, centroids, pitch, closed=False
):
    """Placements of a block that keeps the heading it started with.

    The block hangs behind its head along the direction of travel and is
    centred across it, so it starts on the first electrode and ends on the
    last whatever its shape. It walks the route leg by leg and never steps
    across a corner:

    - **along leg** (parallel to its heading): heads every ``T - overlay``
      electrodes, the block hung behind each;
    - **corner**: it slides on past the corner electrode until centred on
      it, striding as on the along leg; those placements belong to the
      corner;
    - **across leg**: it strides ``W - overlay`` — a locked ``3x1 r`` going
      down strides like a ``1x3 d`` — in one straight run that ends in the
      lanes the *next* leg wants. When those mirror across the route (a
      hairpin in the in / out frame) the run is the leg plus the lane
      shift, and the placements past the leg's last electrode belong to
      it. An across leg that ends the route instead runs until the block's
      leading edge is the last electrode, each placement belonging to that
      leading edge — unless the route is a ``closed`` loop, whose last
      electrode is the start position again.

    Trails of four or more can show a one-cell backward adjustment where an
    across leg meets a return leg: centring an even trail on the corner
    puts the extra cell behind, and the return leg wants it ahead.
    """
    first = leaving_heading(headings)
    nx, ny = left_normal(first)
    width = lanes[0][0] + lanes[0][1] + 1
    along_stride = stride_of(trail_length, trail_overlay)
    across_stride = stride_of(width, trail_overlay)
    last = len(route) - 1

    def leg_heading(j):
        return headings[j] if j else first

    def is_along(heading):
        return axis(heading) in (axis(first), tuple(-c for c in axis(first)))

    def hung(j):
        # The leading cell of a block hung behind head j along its leg: the
        # head itself going forward; T - 1 cells past it, along the block's
        # heading, when the leg runs back against that heading.
        x, y = centroids[route[j]]
        back = 0 if axis(leg_heading(j)) == axis(first) else trail_length - 1

        return (x + back * first[0] * pitch, y + back * first[1] * pitch)

    def centred(point):
        # The leading cell of a block centred on ``point`` along its heading,
        # an even trail keeping its extra cell behind.
        ahead = (trail_length - 1) // 2

        return (
            point[0] + ahead * first[0] * pitch,
            point[1] + ahead * first[1] * pitch,
        )

    index = trail_length - 1
    anchor = hung(index) if is_along(leg_heading(index)) else centroids[route[index]]
    positions = [Position(index, anchor, first, lanes[index])]

    while index < last:
        end = next((j for j in range(index + 1, last) if turns_at(j, headings)), last)
        heading = headings[index + 1]

        if is_along(heading):
            for j in [*range(index + along_stride, end, along_stride), end]:
                positions.append(Position(j, hung(j), first, lanes[j]))

            index = end
            continue

        config = lanes[index]
        corner = centroids[route[index]]

        # Corner: slide on until centred on the corner electrode.
        start = (
            positions[-1].anchor if is_along(leg_heading(index)) else centred(corner)
        )

        for _k, point in run_points(start, centred(corner), along_stride, pitch)[0]:
            positions.append(Position(index, point, first, config))

        # Across: one straight run to the leg's last electrode, shifted to
        # the lanes wanted after it — or, when the route ends here, until
        # the block's leading edge is that electrode.
        final = end == last and not closed

        if final:
            shift = -config[0] if heading[0] * nx + heading[1] * ny > 0 else config[1]
        else:
            shift = lanes[min(end + 1, last)][0] - config[0]

        finish = centred(centroids[route[end]])
        finish = (finish[0] + shift * nx * pitch, finish[1] + shift * ny * pitch)
        points, steps = run_points(centred(corner), finish, across_stride, pitch)
        leg = end - index
        forward = (finish[0] - corner[0]) * headings[end][0] + (
            finish[1] - corner[1]
        ) * headings[end][1] > 0

        for k, point in points:
            if final:
                head = index + k + leg - steps
            else:
                head = min(index + k, end) if forward else end

            positions.append(Position(head, point, first, config))

        index = end

    return positions


# ------------------------------------------------------------------- phases
def trail_phases(
    route, headings, trail_length, trail_overlay, soft_terminate=False, soft_start=False
):
    """The shipped trail algorithm on the route itself — width-1 behaviour,
    ramps included. Each phase belongs to its leading electrode."""
    overlay = min(trail_overlay, trail_length - 1)
    index_phases = PathExecutionService.calculate_trail_phases_for_path(
        route,
        trail_length,
        overlay,
        soft_start=soft_start,
        soft_terminate=soft_terminate,
    )

    return [
        Phase(indices[-1], headings[indices[-1]], [route[i] for i in indices])
        for indices in index_phases
    ]


def hold_phase(route, headings, lanes, centroids, pitch):
    """One phase covering everything a slug too long for its route would
    touch: the union of the 1-deep block at every route electrode."""
    ids = []

    for index, head_id in enumerate(route):
        left, right = lanes[index]

        for electrode_id in block_footprint(
            head_id, headings[index], left, right, 1, centroids, pitch
        ):
            if electrode_id not in ids:
                ids.append(electrode_id)

    return Phase(len(route) - 1, headings[-1], ids)


def keep_count(ids, previous, head_id, centroids, target):
    """``ids`` topped up to ``target`` with the cells of ``previous`` nearest
    the head — the flow rule: a slug against an edge or in a neck keeps its
    actuation count, the liquid piling up behind the head. A slug born
    clipped comes on short, then fills out from its second phase by
    dragging the cells it left behind."""
    if len(ids) >= target or not previous:
        return ids

    head = centroids[head_id]
    carry = sorted(
        (cell for cell in previous if cell not in ids),
        key=lambda cell: math.dist(centroids[cell], head),
    )

    return ids + carry[: target - len(ids)]


def rows_along(ids, heading, centroids, pitch):
    """``ids`` grouped into the block's rows across ``heading``, tail row
    first."""

    def along(cell):
        x, y = centroids[cell]

        return round((x * heading[0] + y * heading[1]) / pitch)

    rows = {}

    for cell in ids:
        rows.setdefault(along(cell), []).append(cell)

    return [rows[key] for key in sorted(rows)]


def ramp_up(phase, centroids, pitch):
    """Soft start: the phases before ``phase`` as its block's rows come on
    one per phase, tail row first — the shipped soft-start ramp, which adds
    one route electrode at a time, done a row at a time."""
    rows = rows_along(phase.ids, phase.heading, centroids, pitch)

    return [
        Phase(phase.head, phase.heading, [cell for row in rows[:count] for cell in row])
        for count in range(1, len(rows))
    ]


def ramp_down(phase, centroids, pitch):
    """Soft end: the phases after ``phase`` as its block's rows go off one
    per phase, tail row first, down to the head row — the mirror of
    :func:`ramp_up`, and for a width-1 trail exactly the shipped
    soft-terminate ramp (### → ## → #)."""
    rows = rows_along(phase.ids, phase.heading, centroids, pitch)

    return [
        Phase(phase.head, phase.heading, [cell for row in rows[count:] for cell in row])
        for count in range(1, len(rows))
    ]


def slug_phases(
    route,
    centroids,
    neighbours,
    left,
    right,
    trail_length,
    trail_overlay,
    pitch=None,
    rotation_lock=False,
    soft_terminate=False,
    lane_frame=LEFT_RIGHT,
    repetitions=1,
    soft_start=False,
):
    """The phases of a slug driven along ``route`` (see the module docstring
    for the rules).

    Parameters
    ----------
    route : electrode ids, each a neighbour of the previous.
    centroids, neighbours : the device geometry.
    left, right : extra lanes on each side of the route.
    trail_length, trail_overlay : as in the route sidebar. A block phase
        advances ``trail_length - trail_overlay`` route electrodes; a
        translating block advances by its extent along the current leg
        minus the overlay, so the overlay may run up to
        ``max(width, trail_length) - 1``.
    pitch : lattice spacing; measured from ``neighbours`` when None.
    rotation_lock : keep the block's orientation fixed through corners and
        only translate it — what a square does regardless.
    soft_terminate : after the last head, take the slug off a row at a
        time from its tail down to the head row.
    lane_frame : ``LEFT_RIGHT`` (``left``/``right`` are screen sides) or
        ``IN_OUT`` (``left`` is the inside count, ``right`` the outside).
    repetitions : how many times a loop plays its cycle before returning
        onto the start electrode; ignored for an open route. Heads then
        index the unrolled route.
    soft_start : before the first full phase, bring the block on a row at
        a time from its tail; a held short route does not ramp.

    Returns
    -------
    ``[Phase]`` in playing order — head, direction of travel, electrodes
    on. Empty for an empty route.
    """
    if not route:
        return []

    if pitch is None:
        pitch = lattice_pitch(centroids, neighbours)

    width = left + right + 1
    translate = rotation_lock or width == trail_length
    cycle_length = len(route) - 1 if is_loop(route) else 0

    # A loop plays as one unrolled route (a cycle too short for the trail
    # simply holds, like any short route).
    if cycle_length:
        route = (
            route[:-1]
            if cycle_length < trail_length
            else unroll(route, repetitions, trail_length)
        )

    headings = route_headings(route, centroids, cycle_length)

    # A locked width-1 slug is a bar that keeps its orientation, so only
    # an unlocked one is the plain route trail.
    if width == 1 and not rotation_lock:
        return trail_phases(
            route, headings, trail_length, trail_overlay, soft_terminate, soft_start
        )

    sides = outer_sides(route, centroids, headings)

    if len(route) < trail_length:
        lanes = lane_counts(headings, sides, left, right, lane_frame, False)
        phases = [hold_phase(route, headings, lanes, centroids, pitch)]
    else:
        lanes = lane_counts(headings, sides, left, right, lane_frame, translate)

        if translate:
            positions = translating_positions(
                route,
                headings,
                lanes,
                trail_length,
                trail_overlay,
                centroids,
                pitch,
                closed=bool(cycle_length),
            )
        else:
            positions = rehung_positions(
                route, headings, lanes, trail_length, trail_overlay, centroids
            )

        phases, previous = [], None
        target = width * trail_length

        for position in positions:
            ids = block_cells(
                position.anchor,
                position.heading,
                *position.lanes,
                trail_length,
                centroids,
                pitch,
            )
            ids = keep_count(ids, previous, route[position.head], centroids, target)

            # Re-hanging at a corner can reproduce the previous footprint (a
            # 2x2 turning); an identical phase would be a no-op, so it is
            # dropped.
            if previous is None or set(ids) != set(previous):
                # The direction of travel: the route's at the head for a
                # translating block, the block's own for a re-hung one.
                travel = headings[position.head] if translate else position.heading
                phases.append(Phase(position.head, travel, ids))
                previous = ids

    if soft_terminate and phases:
        phases += ramp_down(phases[-1], centroids, pitch)

    if soft_start and phases:
        phases = ramp_up(phases[0], centroids, pitch) + phases

    return phases

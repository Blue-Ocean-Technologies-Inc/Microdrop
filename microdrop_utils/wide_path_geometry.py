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
  bends (see :func:`outer_sides` and :func:`lane_counts`). A rotation-
  locked block never re-reads its lanes at a corner, so it always uses
  ``LEFT_RIGHT``; in / out is a distinction for blocks that turn.
- **along / across leg** — for a translating block, a leg parallel to the
  heading it started with, or perpendicular to it.

Phases are simply numbered by their place in the list, as the shipped
executor numbers them. Each carries the route index it belongs to and the
direction of travel there, which is what the notation prints beside the
number.

Electrodes that do not exist — beyond the device edge, inside a reservoir
neck — are left out of a block; nothing is faked in their place. Instead the
**actuation count stays constant**: a clipped block is topped up with the
device electrodes nearest where its unclipped centre would be, so a wall
shifts the slug sideways and only a neck stretches it
(:func:`top_up_to_centre`). Once every phase is known, topped-up phases that
only filled time are trimmed (:func:`trim_wraps`). The count only comes down
at the end of the route, and only with **soft end** on; **soft start** brings
it up the same way, a row at a time (:func:`ramp_down`, :func:`ramp_up`).
"""

# Standard library imports.
import math
import statistics
from collections import namedtuple

# Microdrop utils imports.
from microdrop_utils import route_execution

#: How far (in pitches) a snapped lattice position may be from the nearest
#: electrode centroid and still count as that electrode. Half a pitch: any
#: further and the position is between electrodes, i.e. a hole.
SNAP_TOLERANCE = 0.5

#: How much more a cell's distance along a block's heading counts than its
#: distance across it when a clipped block makes up its count: enough that a
#: wall shifts the slug sideways rather than stretching it along the route.
ALONG_COST = 1.5

#: Lane frames: the two lane counts read as screen-left / screen-right of
#: travel, or as inside / outside of the turn.
LEFT_RIGHT, IN_OUT = "left/right", "in/out"

#: One phase: the route index it belongs to (``head``), the direction of
#: travel there (``heading``), and the electrodes on (``ids``).
Phase = namedtuple("Phase", "head heading ids")

#: One block placement: the route index it belongs to, the ``anchor`` point
#: its leading cell sits on, the ``heading`` it hangs behind that point
#: along, its ``(left, right)`` lane counts across that heading, and whether
#: it was ``forced``: fitted to a point rather than hung behind a route
#: electrode the stride reached — a run's finish (centred on a corner, the
#: leading edge on the route's end, a loop's return to its start) or a route
#: end the stride fell short of.
Position = namedtuple("Position", "head anchor heading lanes forced", defaults=(False,))


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
    last = len(route) - 1
    heads = list(range(trail_length - 1, len(route), stride))
    landed = heads[-1] == last

    if not landed:
        heads.append(last)

    positions = []

    for index in heads:
        anchor = centroids[route[index]]
        forced = index == last and not landed
        positions.append(Position(index, anchor, headings[index], lanes[index], forced))

        if trail_length == 1 and turns_at(index, headings):
            positions.append(
                Position(index, anchor, headings[index + 1], lanes[index + 1])
            )

    return positions


def translating_positions(
    route,
    headings,
    lanes,
    trail_length,
    trail_overlay,
    centroids,
    pitch,
    closed=False,
    recentre=True,
):
    """Placements of a block that keeps the heading it started with.

    The block hangs behind its head along the direction of travel and is
    centred across it, so it starts on the first electrode and ends on the
    last whatever its shape. It walks the route leg by leg and never steps
    across a corner:

    - **along leg** (parallel to its heading): heads every ``T - overlay``
      electrodes, the block hung behind each. Coming off a corner the
      block already lies over the first cells of the leg, so the corner
      placement's head is the leading one of those in the new direction
      of travel and the strides count from it (otherwise a 2x3 turning
      with no overlay crept one cell where its stride is two);
    - **corner**: from its last stride on the leg it slides on past the
      corner electrode until centred on it, striding as on the along leg
      and never stopping on the corner first (with no overlay that stop
      would overlap the stride before it). Each slide placement belongs to
      the leading cell it has reached, the corner once past it;
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

    With ``recentre`` off the block is not centred on an across leg: it
    keeps the position it arrived in, trailing back along the along leg it
    came off, so the route runs along its edge rather than through its
    middle. That saves the centring shift at a corner between two long
    legs and costs one at a one-electrode jog, where the hung position
    flips to the other side of the corner.
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

    # How far back along the block's heading the last along leg left it:
    # nothing when that leg ran with the heading, the whole block behind
    # its head when it ran against.
    arrived_back = 0

    def centred(point):
        # The leading cell of a block centred on ``point`` along its heading,
        # an even trail keeping its extra cell behind — or, with re-centring
        # off, hung as it arrived.
        ahead = (trail_length - 1) // 2 if recentre else arrived_back

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
            start = positions[-1].head
            heads = list(range(start + along_stride, end, along_stride))

            # The leg ends on its last electrode unless a corner slide
            # takes the block on from here.
            if end == last or is_along(headings[end + 1]):
                heads.append(end)

            for j in heads:
                forced = (j - start) % along_stride != 0
                positions.append(Position(j, hung(j), first, lanes[j], forced))

            arrived_back = 0 if axis(heading) == axis(first) else trail_length - 1
            index = end
            continue

        config = lanes[index]
        corner = centroids[route[index]]

        # Corner: slide on until centred on the corner electrode.
        start = (
            positions[-1].anchor if is_along(leg_heading(index)) else centred(corner)
        )
        travel = leg_heading(index)
        back = 0 if axis(travel) == axis(first) else trail_length - 1

        def leading_index(point):
            # The route index of the block's leading cell in the direction
            # of travel; the corner once the block has reached it.
            x = point[0] - back * first[0] * pitch
            y = point[1] - back * first[1] * pitch
            behind = (corner[0] - x) * travel[0] + (corner[1] - y) * travel[1]

            return index - round(max(behind, 0) / pitch)

        points, steps = run_points(start, centred(corner), along_stride, pitch)

        for k, point in points:
            positions.append(
                Position(leading_index(point), point, first, config, k == steps)
            )

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

            positions.append(Position(head, point, first, config, k == steps))

        # Turning onto an along leg: the block centred on the corner covers
        # (T - 1) // 2 cells ahead of it along its heading and T // 2 behind,
        # so its head is the last of those the next leg runs over.
        if end < last and is_along(headings[end + 1]):
            with_heading = axis(headings[end + 1]) == axis(first)

            if recentre:
                covered = (trail_length - 1) // 2 if with_heading else trail_length // 2
            else:
                # Hung, the block reaches T - 1 cells onto a leg that runs
                # back the way it came and none onto one that carries on.
                arrived_with = arrived_back == 0
                covered = 0 if arrived_with == with_heading else trail_length - 1

            next_end = next(
                (j for j in range(end + 1, last) if turns_at(j, headings)), last
            )
            positions[-1] = positions[-1]._replace(head=min(end + covered, next_end))

        index = end

    return positions


# ------------------------------------------------------------------- phases
def trail_phases(
    route, headings, trail_length, trail_overlay, soft_terminate=False, soft_start=False
):
    """The shipped trail algorithm on the route itself — width-1 behaviour,
    ramps included. Each phase belongs to its leading electrode."""
    overlay = min(trail_overlay, trail_length - 1)
    index_phases = route_execution.PathExecutionService.calculate_trail_phases_for_path(
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


def block_phases(
    route,
    headings,
    positions,
    trail_length,
    trail_overlay,
    translate,
    centroids,
    neighbours,
    pitch,
):
    """The phases of a block's placements: its cells at each, topped up to
    the actuation count where clipped, identical repeats and a redundant end
    step dropped, and topped-up phases that only filled time trimmed."""
    width = positions[0].lanes[0] + positions[0].lanes[1] + 1
    target = width * trail_length
    blocks = [
        block_cells(
            position.anchor,
            position.heading,
            *position.lanes,
            trail_length,
            centroids,
            pitch,
        )
        for position in positions
    ]
    phases, wrapped, forced, previous = [], [], [], None

    for index, position in enumerate(positions):
        # Ties between equally near cells go to ones the neighbouring
        # blocks use anyway, to save switching electrodes on and off.
        reuse = set(blocks[index - 1] if index else ())

        if index + 1 < len(blocks):
            reuse |= set(blocks[index + 1])

        centre = block_centre(
            position.anchor, position.heading, *position.lanes, trail_length, pitch
        )
        ids = top_up_to_centre(
            blocks[index],
            centre,
            position.heading,
            reuse,
            target,
            centroids,
            neighbours,
            pitch,
        )

        # Re-hanging at a corner can reproduce the previous footprint (a
        # 2x2 turning); an identical phase would be a no-op, so it is
        # dropped.
        if previous is None or set(ids) != set(previous):
            # The direction of travel: the route's at the head for a
            # translating block, the block's own for a re-hung one.
            travel = headings[position.head] if translate else position.heading
            phases.append(Phase(position.head, travel, ids))
            wrapped.append(len(ids) > len(blocks[index]))
            forced.append(position.forced)
            previous = ids

    # When the last placement was forced onto the route's end — fitted there
    # (an across leg's leading-edge fit, a slide centred on a final corner, a
    # loop's return to its start) or appended past a stride that fell short —
    # and the slug could step there straight from the phase before, the
    # short step between is dropped: a 2x3 closing a loop goes from its last
    # stride to the start footprint in one move instead of via a
    # one-electrode shuffle. An end the stride lands on, the block hung
    # behind it, keeps every step, so the last move never outruns the
    # stride (ruled 2026-09-25).
    if (
        len(phases) >= 3
        and forced[-1]
        and touching(phases[-3].ids, phases[-1].ids, trail_overlay, neighbours)
    ):
        del phases[-2]
        del wrapped[-2]

    stride = max(
        stride_of(trail_length, trail_overlay), stride_of(width, trail_overlay)
    )

    return trim_wraps(phases, wrapped, trail_overlay, stride, neighbours)


def trim_wraps(phases, wrapped, trail_overlay, stride, neighbours):
    """``phases`` without the topped-up ones that only filled time.

    Once every phase is known, a phase that was topped up (``wrapped``) is
    dropped when the phase kept before it and the phase after it already
    step into each other with ``trail_overlay``, and the head moves no
    further between them than ``stride`` — so dropping it never leaves a gap
    and never moves the slug faster than asked.
    """
    kept = []

    for index, phase in enumerate(phases):
        following = phases[index + 1] if index + 1 < len(phases) else None

        if (
            wrapped[index]
            and kept
            and following is not None
            and touching(kept[-1].ids, following.ids, trail_overlay, neighbours)
            and following.head - kept[-1].head <= stride
        ):
            continue

        kept.append(phase)

    return kept


def continuous(phases, neighbours):
    """Whether every phase touches the next, so a droplet can follow them."""
    return all(
        touching(a.ids, b.ids, 0, neighbours) for a, b in zip(phases, phases[1:])
    )


def touching(ids, other, trail_overlay, neighbours):
    """Whether a slug could step from ``ids`` to ``other`` in one phase:
    they share at least ``trail_overlay`` electrodes, and with no overlay
    asked for, they share one or sit side by side."""
    shared = len(set(ids) & set(other))

    if trail_overlay:
        return shared >= trail_overlay

    return shared > 0 or any(
        neighbour in other for cell in ids for neighbour in neighbours.get(cell, ())
    )


def block_centre(anchor, heading, left, right, trail_length, pitch):
    """The centre of the block whose leading cell sits on ``anchor``, as it
    would be with nothing clipped: the mean of every lattice point it spans,
    on the device or not."""
    nx, ny = left_normal(heading)
    along = -(trail_length - 1) / 2
    lane = (left - right) / 2

    return (
        anchor[0] + (along * heading[0] + lane * nx) * pitch,
        anchor[1] + (along * heading[1] + lane * ny) * pitch,
    )


def top_up_to_centre(ids, centre, heading, reuse, target, centroids, neighbours, pitch):
    """``ids`` topped up to ``target`` — the flow rule: a slug against an
    edge or in a neck keeps its actuation count.

    The cells added are the device electrodes nearest ``centre``, where the
    unclipped block's centre would be, with distance along ``heading``
    costing :data:`ALONG_COST` times distance across it. A wall therefore
    shifts the slug sideways (a clipped lane reappears on the other side of
    the route) and only a neck, clipped on both sides, stretches it along
    the route — the slug stays centred where the plain block would be, full
    from its first phase. Ties go to cells in ``reuse``, then by position.

    An added cell must touch the slug (the block or a cell already added),
    since liquid cannot be in two places: the top-up grows outward and
    stops short of the count rather than strand cells across a gap.
    """
    if len(ids) >= target:
        return ids

    nx, ny = left_normal(heading)

    def cost(cell):
        dx = (centroids[cell][0] - centre[0]) / pitch
        dy = (centroids[cell][1] - centre[1]) / pitch
        along = dx * heading[0] + dy * heading[1]
        across = dx * nx + dy * ny

        return round(math.hypot(along * ALONG_COST, across), 6)

    ids = list(ids)
    pool = sorted(
        (cell for cell in centroids if cell not in ids),
        key=lambda cell: (
            cost(cell),
            cell not in reuse,
            centroids[cell][1],
            centroids[cell][0],
        ),
    )

    while len(ids) < target:
        added = next(
            (
                cell
                for cell in pool
                if any(neighbour in ids for neighbour in neighbours.get(cell, ()))
            ),
            None,
        )

        if added is None:
            break

        ids.append(added)
        pool.remove(added)

    return ids


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
    recentre=True,
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
        ``max(width, trail_length) - 1``. An overlay too small for the
        block to move without a gap plays as the smallest one that does.
    pitch : lattice spacing; measured from ``neighbours`` when None.
    rotation_lock : keep the block's orientation fixed through corners and
        only translate it — what a square does regardless. A locked block
        reads its lanes as screen left / right whatever ``lane_frame`` says.
    soft_terminate : after the last head, take the slug off a row at a
        time from its tail down to the head row.
    lane_frame : ``LEFT_RIGHT`` (``left``/``right`` are screen sides) or
        ``IN_OUT`` (``left`` is the inside count, ``right`` the outside).
    repetitions : how many times a loop plays its cycle before returning
        onto the start electrode; ignored for an open route. Heads then
        index the unrolled route.
    soft_start : before the first full phase, bring the block on a row at
        a time from its tail; a held short route does not ramp.
    recentre : a rotation-locked block is centred on the route along an
        across leg; off, it keeps the position it arrived in (see
        :func:`translating_positions`). Nothing to a block that re-hangs.

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

    if rotation_lock:
        lane_frame = LEFT_RIGHT

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

        def phases_with(overlay):
            if translate:
                positions = translating_positions(
                    route,
                    headings,
                    lanes,
                    trail_length,
                    overlay,
                    centroids,
                    pitch,
                    closed=bool(cycle_length),
                    recentre=recentre,
                )
            else:
                positions = rehung_positions(
                    route, headings, lanes, trail_length, overlay, centroids
                )

            return block_phases(
                route,
                headings,
                positions,
                trail_length,
                overlay,
                translate,
                centroids,
                neighbours,
                pitch,
            )

        # A long trail with a small overlay can leave a gap: a re-hung
        # block whose stride crosses a corner hangs its tail off the route,
        # and the electrodes before the corner are in neither phase. A
        # droplet cannot cross a gap, so the overlay is raised until every
        # phase touches the next; small overlays on a long trail all play
        # as the smallest one that moves the slug continuously.
        for overlay in range(
            trail_overlay, max(width, trail_length, trail_overlay + 1)
        ):
            phases = phases_with(overlay)

            if continuous(phases, neighbours):
                break

    if soft_terminate and phases:
        phases += ramp_down(phases[-1], centroids, pitch)

    if soft_start and phases:
        phases = ramp_up(phases[0], centroids, pitch) + phases

    return phases

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""``slug_phases`` against the corner-turning game answers.

``wide_path_answers.json`` holds, per case, the phase sequence of the
candidate the maintainer picked in the game (2026-09-09, revised
2026-09-10): slug shapes, edge and neck clipping on a synthetic grid and on
the bundled 2x3 device, rotation-locked shapes, in / out lanes on hairpins
(locked and not), loops and their seams, and trails that don't fit — the
nine open questions of 2026-09-11 were all answered "as current".
Cases the board-audit rules of 2026-09-15/16 changed were re-derived on
2026-09-25, each with a note naming its rule. The algorithm must reproduce
every one. Cases answered "none" are left out.
"""

# Standard library imports.
import json
from pathlib import Path
from textwrap import dedent

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.wide_path_geometry import (
    IN_OUT,
    LEFT_RIGHT,
    lattice_pitch,
    left_normal,
    outer_sides,
    slug_phases,
    unroll,
)
from microdrop_utils.wide_path_notation import (
    frame_text,
    heading_letter,
    lattice_cells,
    render_phases,
    shorthand,
)

ANSWERS = json.loads(
    Path(__file__).with_name("wide_path_answers.json").read_text(encoding="utf-8")
)

#: The bundled 2x3 device as centroids and neighbours, captured once from
#: ``device_viewer/resources/devices/2x3device.svg`` so these tests parse no
#: SVG and import no plugin. Regenerate it if that device changes.
DEVICE_2X3 = json.loads(
    Path(__file__).with_name("wide_path_device_2x3.json").read_text(encoding="utf-8")
)


def square_lattice(n=11):
    centroids = {
        f"e{x:02d}{y:02d}": (float(x), float(y)) for x in range(n) for y in range(n)
    }
    neighbours = {
        f"e{x:02d}{y:02d}": [
            f"e{a:02d}{b:02d}"
            for a, b in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
            if 0 <= a < n and 0 <= b < n
        ]
        for x in range(n)
        for y in range(n)
    }
    return centroids, neighbours, 1.0


@pytest.fixture(scope="module")
def lattices():
    centroids = {k: tuple(v) for k, v in DEVICE_2X3["centroids"].items()}
    neighbours = DEVICE_2X3["neighbours"]
    return {
        "square": square_lattice(),
        "device": (centroids, neighbours, lattice_pitch(centroids, neighbours)),
    }


@pytest.mark.parametrize(
    "case", [pytest.param(case, id=case["id"]) for case in ANSWERS]
)
def test_slug_phases_reproduce_the_picked_candidate(case, lattices):
    centroids, neighbours, pitch = lattices[case["lattice"]]
    phases = slug_phases(
        case["route"],
        centroids,
        neighbours,
        case["left"],
        case["right"],
        case["trail"],
        case["overlay"],
        pitch=pitch,
        rotation_lock=case.get("rotation_lock", False),
        soft_terminate=case.get("soft_terminate", False),
        lane_frame=case.get("lane_frame", LEFT_RIGHT),
        repetitions=case.get("repetitions", 1),
        soft_start=case.get("soft_start", False),
    )
    assert [sorted(phase.ids) for phase in phases] == [
        p["ids"] for p in case["phases"]
    ], f"{case['id']}: expected candidate {case['pick']}"
    assert [(phase.head, heading_letter(phase.heading)) for phase in phases] == [
        (p["head"], p["heading"]) for p in case["phases"]
    ]


def test_square_slug_hangs_behind_its_head_from_first_to_last_electrode():
    """A square starts on the first electrode and ends with its leading edge
    on the last electrode (2026-09-11: it used to start one in and end one
    past). Since the board audit (2139af4e) it steps from its last stride
    straight to that end placement: the corner slide, which shared the
    overlay with both, is dropped."""
    centroids, neighbours, pitch = square_lattice()
    route = ["e0205", "e0305", "e0405", "e0505", "e0504", "e0503"]
    phases = slug_phases(route, centroids, neighbours, 1, 1, 3, 2, pitch=pitch)
    assert frame_text(render_phases(phases, route, centroids, pitch)) == dedent(
        """
        1 r             2 r             3 u
        . . . . . . .   . . . . . . .   . . . . . . .
        . . . . . . .   . . . . . . .   . . . # # # .
        . # # # . . .   . . # # # . .   . . . # # # .
        . # # # . . .   . . # # # . .   . . . # # # .
        . # # # . . .   . . # # # . .   . . . . . . .
        . . . . . . .   . . . . . . .   . . . . . . .
        """
    ).strip("\n")


def test_rectangle_re_hangs_behind_the_head_at_the_corner():
    # The stride lands on the last electrode, a natural end, so the re-hang
    # behind head 3 stays: the end-of-route drop (2139af4e) only follows a
    # placement forced onto the route's end (2026-09-25).
    centroids, neighbours, pitch = square_lattice()
    route = ["e0305", "e0405", "e0505", "e0504", "e0503"]
    phases = slug_phases(route, centroids, neighbours, 1, 1, 2, 1, pitch=pitch)
    assert frame_text(render_phases(phases, route, centroids, pitch)) == dedent(
        """
        1 r           2 r           3 u           4 u
        . . . . . .   . . . . . .   . . . . . .   . . . . . .
        . . . . . .   . . . . . .   . . . . . .   . . # # # .
        . # # . . .   . . # # . .   . . # # # .   . . # # # .
        . # # . . .   . . # # . .   . . # # # .   . . . . . .
        . # # . . .   . . # # . .   . . . . . .   . . . . . .
        . . . . . .   . . . . . .   . . . . . .   . . . . . .
        """
    ).strip("\n")


def test_overlay_sets_how_many_electrodes_a_block_advances():
    centroids, neighbours, pitch = square_lattice()
    route = [f"e{x:02d}05" for x in range(1, 10)]
    hop = slug_phases(route, centroids, neighbours, 1, 1, 3, 0, pitch=pitch)
    assert [phase.head for phase in hop] == [2, 5, 8]


def test_a_high_overlay_creeps_one_electrode_at_a_time_to_the_end():
    # The stride lands on the last electrode, so the end-of-route drop
    # (2139af4e) stays out of it: the last move never outruns the stride.
    centroids, neighbours, pitch = square_lattice()
    route = [f"e{x:02d}05" for x in range(1, 10)]
    creep = slug_phases(route, centroids, neighbours, 1, 1, 3, 2, pitch=pitch)
    assert [phase.head for phase in creep] == [2, 3, 4, 5, 6, 7, 8]


def test_width_one_is_the_shipped_trail_and_short_routes_hold():
    centroids, neighbours, pitch = square_lattice()
    route = ["e0405", "e0505", "e0504", "e0503"]
    snake = slug_phases(route, centroids, neighbours, 0, 0, 2, 1, pitch=pitch)
    assert [sorted(phase.ids) for phase in snake] == [
        ["e0405", "e0505"],
        ["e0504", "e0505"],
        ["e0503", "e0504"],
    ]
    held = slug_phases(route[:3], centroids, neighbours, 1, 0, 4, 3, pitch=pitch)
    assert len(held) == 1 and sorted(held[0].ids) == [
        "e0404",
        "e0405",
        "e0504",
        "e0505",
    ]


def test_a_bar_shows_both_orientations_on_the_corner_electrode():
    centroids, neighbours, pitch = square_lattice()
    route = ["e0305", "e0405", "e0505", "e0504", "e0503"]
    phases = slug_phases(route, centroids, neighbours, 1, 1, 1, 0, pitch=pitch)
    # The corner electrode (head 2) gets two phases: arriving, then departing.
    assert [phase.head for phase in phases] == [0, 1, 2, 2, 3, 4]
    assert [heading_letter(p.heading) for p in phases] == ["r", "r", "r", "u", "u", "u"]
    assert sorted(phases[2].ids) == ["e0504", "e0505", "e0506"]  # arriving, vertical
    assert sorted(phases[3].ids) == ["e0405", "e0505", "e0605"]  # departing, flat


def test_a_one_electrode_leg_between_two_turns_shows_both_turns():
    centroids, neighbours, pitch = square_lattice()
    # Right along y=5, one step down at x=5, right along y=6.
    route = ["e0205", "e0305", "e0405", "e0505", "e0506", "e0606", "e0706"]
    phases = slug_phases(route, centroids, neighbours, 1, 1, 1, 0, pitch=pitch)
    assert [phase.head for phase in phases] == [0, 1, 2, 3, 3, 4, 4, 5, 6]
    # The jog electrode lies flat across the down heading, then stands up
    # again for the leg that follows.
    assert sorted(phases[5].ids) == ["e0406", "e0506", "e0606"]
    assert sorted(phases[6].ids) == ["e0505", "e0506", "e0507"]


def test_rotation_lock_translates_a_rectangle_without_rotating_it():
    centroids, neighbours, pitch = square_lattice()
    route = ["e0305", "e0405", "e0505", "e0504", "e0503"]
    locked = slug_phases(
        route, centroids, neighbours, 1, 1, 2, 1, pitch=pitch, rotation_lock=True
    )
    # A 3x2 heading right stays three tall and two wide as it goes up: 2x3 u.
    # It ends with its leading edge on the last electrode, stepping there
    # straight from its start: the two share the overlay, so the corner stop
    # between them is dropped (2139af4e).
    assert frame_text(render_phases(locked, route, centroids, pitch)) == dedent(
        """
        1 r         2 u
        . . . . .   . . . . .
        . . . . .   . . # # .
        . # # . .   . . # # .
        . # # . .   . . # # .
        . # # . .   . . . . .
        . . . . .   . . . . .
        """
    ).strip("\n")
    assert shorthand(1, 1, 2, (0.0, -1.0), block_heading=(1.0, 0.0)) == "2x3 u"
    assert shorthand(1, 1, 2, (1.0, 0.0), block_heading=(1.0, 0.0)) == "3x2 r"


def test_locked_bar_strides_by_its_width_across_its_heading():
    """A locked ``3x1 r`` going up is a ``1x3 u``: the overlay governs the
    stride on that leg as it would for a trail of 3, and a step never
    crosses the corner."""
    centroids, neighbours, pitch = square_lattice()
    route = ["e0205", "e0305", "e0405", "e0505", "e0504", "e0503", "e0502", "e0501"]

    def heads(overlay):
        phases = slug_phases(
            route,
            centroids,
            neighbours,
            1,
            1,
            1,
            overlay,
            pitch=pitch,
            rotation_lock=True,
        )
        return [phase.head for phase in phases], phases

    # The leg is four long but the bar ends hung behind the last electrode,
    # so the run is three; on that final leg a phase belongs to the block's
    # leading edge.
    hop, phases = heads(0)
    assert hop == [0, 1, 2, 3, 7]
    assert sorted(phases[-1].ids) == ["e0501", "e0502", "e0503"]
    assert heads(1)[0] == [0, 1, 2, 3, 6, 7]
    assert heads(2)[0] == [0, 1, 2, 3, 5, 6, 7]
    assert sorted(heads(2)[1][5].ids) == ["e0502", "e0503", "e0504"]


def test_a_2x2_keeps_four_actuations_into_a_neck_and_drains_with_soft_end(lattices):
    """The maintainer's drawing for "2x2 into the neck" (2026-09-10), bar
    the soft end, which drops rows rather than cells since 2026-09-11: four
    electrodes stay on as the slug enters the 1-wide reservoir feed, the
    cell farthest from the head dropping first, then it drains to the last
    electrode. Since the board audit (2139af4e) the drawing's "4 u" frame is
    dropped: the phases either side of it share the overlay, so the slug
    steps straight to its end placement, the drawing's "5 u"."""
    centroids, neighbours, pitch = lattices["device"]
    by_cell = {cell: eid for eid, cell in lattice_cells(centroids, pitch).items()}
    route = [
        by_cell[c] for c in [(6, 8), (7, 8), (8, 8), (8, 7), (8, 6), (8, 5), (8, 4)]
    ]
    phases = slug_phases(
        route, centroids, neighbours, 1, 0, 2, 1, pitch=pitch, soft_terminate=True
    )
    # Soft end goes row by row (2026-09-11), so the two-cell tail row drops
    # first: 4, 2, 1 where the drawing went 4, 3, 2, 1.
    assert [len(phase.ids) for phase in phases] == [4, 4, 4, 4, 2, 1]
    cells = lambda ids: sorted(lattice_cells(centroids, pitch)[i] for i in ids)  # noqa: E731
    # The drawing's "5 u" frame is the fourth phase.
    assert cells(phases[3].ids) == [(7, 6), (8, 4), (8, 5), (8, 6)]
    assert cells(phases[4].ids) == [(8, 4), (8, 5)]
    assert cells(phases[5].ids) == [(8, 4)]
    # Without soft end the slug simply stops, four electrodes on.
    kept = slug_phases(route, centroids, neighbours, 1, 0, 2, 1, pitch=pitch)
    assert [len(phase.ids) for phase in kept] == [4, 4, 4, 4]


def test_a_bar_against_the_right_edge_keeps_three_actuations():
    centroids, neighbours, pitch = square_lattice()
    # Right along y=5 into the last column, then up: the right lane is off.
    route = ["e0805", "e0905", "e1005", "e1004", "e1003"]
    phases = slug_phases(route, centroids, neighbours, 1, 1, 1, 0, pitch=pitch)
    assert all(len(phase.ids) == 3 for phase in phases)
    # The missing lane is made up with the electrode nearest the bar's
    # unclipped centre, a step along the heading costing 1.5 times a step
    # across (6484f26e): at the end that is the cell behind the head. The
    # topped-up phases between the corner and the end are trimmed, their
    # neighbours already touching within the stride.
    assert [phase.head for phase in phases] == [0, 1, 2, 4]
    assert sorted(phases[-1].ids) == ["e0903", "e1003", "e1004"]


def test_in_out_lanes_hug_the_outer_rung_of_a_track():
    """A loop turning left at every corner: with no inside lane and two
    outside lanes every phase lies on the screen-right of travel — the
    outer rung — whichever way the route is heading."""
    centroids, neighbours, pitch = square_lattice()
    # Clockwise on screen? No: right, up, left, down — a left turn each time.
    route = (
        [f"e{x:02d}08" for x in range(2, 8)]
        + [f"e07{y:02d}" for y in range(7, 1, -1)]
        + [f"e{x:02d}02" for x in range(6, 1, -1)]
        + [f"e02{y:02d}" for y in range(3, 8)]
    )
    phases = slug_phases(
        route, centroids, neighbours, 0, 2, 1, 0, pitch=pitch, lane_frame=IN_OUT
    )
    for number, phase in enumerate(phases, 1):
        head = centroids[route[phase.head]]
        lane_cells = [i for i in phase.ids if i != route[phase.head]]
        assert len(lane_cells) == 2, number
        for electrode_id in lane_cells:
            x, y = centroids[electrode_id]
            # Screen-right of travel: negative along the left normal.
            nx, ny = left_normal(phase.heading)
            assert (x - head[0]) * nx + (y - head[1]) * ny < 0, number


def test_in_out_regresses_to_left_right_on_a_straight_route():
    centroids, neighbours, pitch = square_lattice()
    route = [f"e{x:02d}05" for x in range(2, 7)]
    in_out = slug_phases(
        route, centroids, neighbours, 1, 0, 1, 0, pitch=pitch, lane_frame=IN_OUT
    )
    left_right = slug_phases(route, centroids, neighbours, 1, 0, 1, 0, pitch=pitch)
    assert in_out == left_right


def test_outer_sides_follow_the_turn_ahead_and_flip_through_an_s_bend():
    centroids, _neighbours, _pitch = square_lattice()
    # Right, up (a left turn: outside is screen-right, -1), right (a right
    # turn: outside is screen-left, +1), then up again (left turn).
    route = ["e0205", "e0305", "e0304", "e0303", "e0403", "e0503", "e0502", "e0501"]
    assert outer_sides(route, centroids) == [-1, -1, 1, 1, -1, -1, -1, -1]
    assert outer_sides(["e0205", "e0305", "e0405"], centroids) == [-1, -1, -1]


RING = ["e0303", "e0403", "e0503", "e0504", "e0505", "e0405", "e0305", "e0304", "e0303"]


def test_loop_plays_its_cycle_and_returns_onto_the_start():
    """A route closed on its first electrode is a loop (the device viewer's
    rule): a 3x1 bar goes twice round an 8-ring, turning at the start
    electrode too, and ends where it began."""
    centroids, neighbours, pitch = square_lattice()
    phases = slug_phases(
        RING, centroids, neighbours, 1, 1, 1, 0, pitch=pitch, repetitions=2
    )
    heads = [phase.head for phase in phases]
    assert len(unroll(RING, 2, 1)) == 17 and heads[-1] == 16
    # The seam is a corner: arriving row, then departing row, on both laps.
    assert heads[:3] == [0, 0, 1] and heads.count(8) == 2
    assert len(phases) == 25
    first, last = phases[0].ids, phases[-1].ids
    assert sorted(first) == sorted(last) == ["e0203", "e0303", "e0403"]
    frames = render_phases(phases, unroll(RING, 2, 1), centroids, pitch)
    assert [title for title, _picture in frames[:2]] == ["1 u", "2 r"]


def test_locked_bar_on_a_loop_clamps_its_stride_at_every_corner():
    centroids, neighbours, pitch = square_lattice()
    phases = slug_phases(
        RING,
        centroids,
        neighbours,
        1,
        1,
        1,
        0,
        pitch=pitch,
        repetitions=2,
        rotation_lock=True,
    )
    # Along legs stride 1; across legs (two long) a stride of 3 is clamped.
    # The loop closes in one move (2139af4e): from head 13 the bar already
    # touches its start footprint, so the stop at head 14 is dropped.
    assert [phase.head for phase in phases] == [
        0,
        1,
        2,
        4,
        5,
        6,
        8,
        9,
        10,
        12,
        13,
        16,
    ]


def test_loop_shorter_than_the_trail_holds_its_cycle():
    centroids, neighbours, pitch = square_lattice()
    phases = slug_phases(
        ["e0303", "e0403", "e0303"],
        centroids,
        neighbours,
        1,
        0,
        3,
        2,
        pitch=pitch,
        repetitions=3,
    )
    assert [sorted(phase.ids) for phase in phases] == [
        ["e0302", "e0303", "e0402", "e0403"]
    ]


def test_soft_start_brings_a_block_on_row_by_row_from_the_tail():
    centroids, neighbours, pitch = square_lattice()
    route = ["e0205", "e0305", "e0405", "e0505", "e0504", "e0503"]
    phases = slug_phases(
        route, centroids, neighbours, 1, 1, 3, 2, pitch=pitch, soft_start=True
    )
    # A 3x3 hangs behind head 2: rows at x = 2, 3, 4, tail first.
    assert [phase.head for phase in phases][:4] == [2, 2, 2, 3]
    assert sorted(phases[0].ids) == ["e0204", "e0205", "e0206"]
    assert sorted(phases[1].ids) == sorted(phases[0].ids + ["e0304", "e0305", "e0306"])
    assert len(phases[2].ids) == 9
    # A bar is one row: nothing to ramp. A width-1 trail gets the shipped ramp.
    bar = slug_phases(
        route, centroids, neighbours, 1, 1, 1, 0, pitch=pitch, soft_start=True
    )
    assert [phase.head for phase in bar][:2] == [0, 1]
    trail = slug_phases(
        route, centroids, neighbours, 0, 0, 3, 2, pitch=pitch, soft_start=True
    )
    assert [(phase.head, len(phase.ids)) for phase in trail][:3] == [
        (0, 1),
        (1, 2),
        (2, 3),
    ]


def test_departing_row_takes_the_side_of_the_leg_it_departs_onto():
    """A 2x1 bar (one outside lane) round the first corner of an S-bend,
    right, down, right (2026-09-11). The corner's departing row belongs to
    the down leg, whose outside is decided by the turn ahead, so its lane
    sits where the next phase will have it instead of swinging across."""
    centroids, neighbours, pitch = square_lattice()
    route = ["e0203", "e0303", "e0403", "e0404", "e0504", "e0604"]
    phases = slug_phases(
        route, centroids, neighbours, 0, 1, 1, 0, pitch=pitch, lane_frame=IN_OUT
    )
    # Head 2 arriving (lane above), head 2 departing (lane west, where the
    # down leg wants it), head 3 (lane west).
    assert [(phase.head, heading_letter(phase.heading)) for phase in phases[2:5]] == [
        (2, "r"),
        (2, "d"),
        (3, "d"),
    ]
    assert sorted(phases[2].ids) == ["e0402", "e0403"]
    assert sorted(phases[3].ids) == ["e0303", "e0403"]
    assert sorted(phases[4].ids) == ["e0304", "e0404"]

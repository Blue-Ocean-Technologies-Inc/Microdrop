# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The execution plan builder with a slug shape.

At width 1 the plan must be byte-for-byte what it was before the shape
existed: ``wide_path_plan_golden.json`` holds twelve plans captured from the
untouched builder (2026-09-11) — open paths, loops with and without the
repeat-duration cap, ramps, linear repeats, several paths at once. Wider
slugs take their phases from ``slug_phases`` and get the same step-level
layout.
"""

# Standard library imports.
import json
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.route_execution import PathExecutionService
from microdrop_utils.tests.test_wide_path_slug_phases import square_lattice
from microdrop_utils.wide_path_geometry import LEFT_RIGHT, slug_phases

GOLDEN = json.loads(
    Path(__file__).with_name("wide_path_plan_golden.json").read_text(encoding="utf-8")
)
RING = ["e0303", "e0403", "e0503", "e0504", "e0505", "e0405", "e0305", "e0304", "e0303"]
LINE = ["e0205", "e0305", "e0405", "e0505", "e0605", "e0705"]
L_ROUTE = ["e0205", "e0305", "e0405", "e0505", "e0504", "e0503"]


def plan_electrodes(plan):
    return [sorted(item["activated_electrodes"]) for item in plan]


@pytest.mark.parametrize("case", GOLDEN, ids=[case["name"] for case in GOLDEN])
def test_width_one_plans_are_unchanged(case):
    plan = PathExecutionService.calculate_execution_plan_from_params(**case["params"])

    assert plan_electrodes(plan) == plan_electrodes(case["plan"])
    assert [item["time"] for item in plan] == [item["time"] for item in case["plan"]]


def wide_plan(paths, left, right, trail_length, trail_overlay, **options):
    centroids, neighbours, _pitch = square_lattice()

    return PathExecutionService.calculate_execution_plan_from_params(
        duration=1.0,
        repetitions=options.pop("repetitions", 1),
        repeat_duration=options.pop("repeat_duration", 0),
        trail_length=trail_length,
        trail_overlay=trail_overlay,
        paths=paths,
        lane_left=left,
        lane_right=right,
        lane_frame=LEFT_RIGHT,
        rotation_lock=False,
        centroids=centroids,
        neighbours=neighbours,
        **options,
    )


def test_a_wide_open_path_plays_its_slug_phases_with_the_static_electrodes():
    centroids, neighbours, pitch = square_lattice()
    plan = wide_plan([L_ROUTE], 1, 1, 1, 0, activated_electrodes=["e0909"])
    expected = slug_phases(
        L_ROUTE, centroids, neighbours, 1, 1, 1, 0, pitch=pitch, lane_frame=LEFT_RIGHT
    )

    assert plan_electrodes(plan) == [
        sorted(phase.ids + ["e0909"]) for phase in expected
    ]
    assert [item["time"] for item in plan] == [float(i) for i in range(len(expected))]


def test_two_wide_paths_are_merged_per_phase_and_padded_to_the_longer():
    centroids, neighbours, pitch = square_lattice()
    plan = wide_plan([LINE, L_ROUTE], 1, 0, 2, 1)
    line = slug_phases(
        LINE, centroids, neighbours, 1, 0, 2, 1, pitch=pitch, lane_frame=LEFT_RIGHT
    )
    bend = slug_phases(
        L_ROUTE, centroids, neighbours, 1, 0, 2, 1, pitch=pitch, lane_frame=LEFT_RIGHT
    )

    assert len(plan) == max(len(line), len(bend))
    assert plan_electrodes(plan)[0] == sorted(set(line[0].ids) | set(bend[0].ids))
    # The shorter path simply drops out once it is finished.
    assert plan_electrodes(plan)[-1] == sorted(line[-1].ids)


def test_linear_repeats_replay_a_wide_open_path():
    plan = wide_plan([LINE], 1, 0, 1, 0, repetitions=3, linear_repeats=True)
    once = wide_plan([LINE], 1, 0, 1, 0)

    assert plan_electrodes(plan) == plan_electrodes(once) * 3


def test_a_wide_loop_plays_its_repetitions_and_returns():
    centroids, neighbours, pitch = square_lattice()
    plan = wide_plan([RING], 1, 1, 1, 0, repetitions=2, repeat_duration_mode=False)
    expected = slug_phases(
        RING,
        centroids,
        neighbours,
        1,
        1,
        1,
        0,
        pitch=pitch,
        lane_frame=LEFT_RIGHT,
        repetitions=2,
    )

    assert plan_electrodes(plan) == [sorted(phase.ids) for phase in expected]
    assert plan_electrodes(plan)[0] == plan_electrodes(plan)[-1]


def test_repeat_duration_caps_a_wide_loop_and_pads_with_the_return_position():
    # One lap of the 3x1 bar round the ring is 12 phases (8 heads, 4
    # departing rows); 30 s at 1 s a phase fits two laps, the rest idles.
    plan = wide_plan([RING], 1, 1, 1, 0, repetitions=5, repeat_duration=30)
    two_laps = wide_plan([RING], 1, 1, 1, 0, repetitions=2, repeat_duration_mode=False)

    assert len(plan) == 30
    assert plan_electrodes(plan)[: len(two_laps)] == plan_electrodes(two_laps)
    assert all(
        cells == plan_electrodes(two_laps)[-1]
        for cells in plan_electrodes(plan)[len(two_laps) :]
    )


def test_soft_end_ramps_after_the_idle_padding():
    # A 3x2 block (a bar is one row and has nothing to ramp). In repeat-
    # duration mode the laps are decided by the time, as for width 1: as
    # many whole laps as fit in 28 s less the return, then idle phases hold
    # the return position, then the tail row goes off.
    lap = len(
        wide_plan([RING], 1, 1, 2, 1, repetitions=2, repeat_duration_mode=False)
    ) - len(wide_plan([RING], 1, 1, 2, 1, repetitions=1, repeat_duration_mode=False))
    laps = int((28 - 1) / lap)
    active = wide_plan([RING], 1, 1, 2, 1, repetitions=laps, repeat_duration_mode=False)
    plan = wide_plan(
        [RING], 1, 1, 2, 1, repetitions=1, repeat_duration=28, soft_terminate=True
    )
    cells = plan_electrodes(plan)

    assert laps > 1 and cells[: len(active)] == plan_electrodes(active)
    idle = 28 - len(active)
    assert idle >= 1 and len(plan) == 28 + 1
    assert len({tuple(c) for c in cells[len(active) : -1]}) == 1
    assert len(cells[-1]) == 3


def test_a_wide_slug_needs_the_device_geometry():
    with pytest.raises(ValueError, match="centroids"):
        PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0,
            repetitions=1,
            repeat_duration=0,
            trail_length=1,
            trail_overlay=0,
            paths=[LINE],
            lane_left=1,
        )


def test_rep_breakdown_measures_a_wide_loop_lap_in_slug_phases():
    # The 3x1 bar's lap round the ring is 12 phases (see the cap test
    # above), so 30 s at 1 s a phase is two reps of 12 -- not the three
    # reps of 8 the trail's cycle would give.
    centroids, neighbours, _pitch = square_lattice()
    plan = wide_plan([RING], 1, 1, 1, 0, repetitions=5, repeat_duration=30)
    breakdown = PathExecutionService.calculate_phase_rep_breakdown(
        [RING],
        len(plan),
        duration=1.0,
        repetitions=5,
        repeat_duration=30,
        trail_length=1,
        trail_overlay=0,
        lane_left=1,
        lane_right=1,
        lane_frame=LEFT_RIGHT,
        rotation_lock=False,
        centroids=centroids,
        neighbours=neighbours,
    )

    assert breakdown == (12, 2)


def test_rep_breakdown_at_width_one_is_the_trail_cycle():
    centroids, neighbours, _pitch = square_lattice()
    breakdown = PathExecutionService.calculate_phase_rep_breakdown(
        [RING],
        30,
        duration=1.0,
        repetitions=5,
        repeat_duration=30,
        trail_length=1,
        trail_overlay=0,
        centroids=centroids,
        neighbours=neighbours,
    )

    assert breakdown == (8, 3)

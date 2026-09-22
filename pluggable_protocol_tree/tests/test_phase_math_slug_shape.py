# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The slug shape in a protocol run (#682): phase_math reads it off the
row, keeps the device lattice the sync controller hands it, and passes both
to the plan builder — or runs at width 1, and says so, when no lattice is
known."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.route_execution import PathExecutionService
from microdrop_utils.tests.test_wide_path_slug_phases import square_lattice
from microdrop_utils.wide_path_geometry import IN_OUT, LEFT_RIGHT

# Local imports.
from ..services import phase_math
from ..services.phase_math import (
    duration_loop_parts,
    effective_repetitions_for_duration,
    iter_phases,
    set_device_lattice,
    slug_shape_for_row,
)

L_ROUTE = ["e0205", "e0305", "e0405", "e0505", "e0504", "e0503"]
RING = ["e0303", "e0403", "e0503", "e0504", "e0505", "e0405", "e0305", "e0304", "e0303"]


@pytest.fixture
def lattice():
    centroids, neighbours, _pitch = square_lattice()
    set_device_lattice(centroids, neighbours)
    yield centroids, neighbours
    set_device_lattice(None, None)


def test_a_row_without_the_shape_reads_as_the_plain_trail():
    shape = slug_shape_for_row(SimpleNamespace())

    assert shape == {
        "lane_left": 0,
        "lane_right": 0,
        "lane_frame": IN_OUT,
        "rotation_lock": True,
    }


def test_a_row_with_the_shape_maps_to_the_builder_arguments():
    row = SimpleNamespace(
        lane_left=1, lane_right=2, lanes_in_out=False, rotation_lock=False
    )

    assert slug_shape_for_row(row) == {
        "lane_left": 1,
        "lane_right": 2,
        "lane_frame": LEFT_RIGHT,
        "rotation_lock": False,
    }


def test_iter_phases_plays_the_wide_slug_with_the_known_lattice(lattice):
    centroids, neighbours = lattice
    phases = list(
        iter_phases(
            ["e0909"],
            [L_ROUTE],
            trail_length=1,
            lane_left=1,
            lane_right=1,
            rotation_lock=False,
        )
    )
    plan = PathExecutionService.calculate_execution_plan_from_params(
        duration=1.0,
        repetitions=1,
        repeat_duration=0.0,
        trail_length=1,
        trail_overlay=0,
        paths=[L_ROUTE],
        activated_electrodes=["e0909"],
        lane_left=1,
        lane_right=1,
        rotation_lock=False,
        centroids=centroids,
        neighbours=neighbours,
    )

    assert phases == [set(item["activated_electrodes"]) for item in plan]
    assert all(len(phase) == 4 for phase in phases)  # a 3x1 bar plus the static one


def test_without_a_lattice_a_wide_slug_runs_one_wide_and_logs_it(caplog):
    set_device_lattice(None, None)
    caplog.set_level("ERROR")
    wide = list(iter_phases([], [L_ROUTE], trail_length=1, lane_left=1, lane_right=1))
    narrow = list(iter_phases([], [L_ROUTE], trail_length=1))

    assert wide == narrow
    assert "device lattice is unknown" in caplog.text


def test_duration_loop_parts_take_the_shape_too(lattice):
    ramp, unit_cycle, _return = duration_loop_parts(
        [], [L_ROUTE], trail_length=1, lane_left=1, lane_right=1, rotation_lock=False
    )

    assert ramp == []
    assert all(len(phase) == 3 for phase in unit_cycle)


def test_the_lattice_is_module_state_set_by_the_sync_controller():
    centroids, neighbours, _pitch = square_lattice()
    set_device_lattice(centroids, neighbours)

    assert phase_math._device_lattice["centroids"] == centroids

    set_device_lattice(None, None)

    assert phase_math._device_lattice == {"centroids": None, "neighbours": None}


def test_effective_repetitions_count_the_wide_loop_in_laps_of_the_slug(lattice):
    # The Route Reps knob derived from a duration: two laps of the 3x1
    # bar (12 phases each) fit 30 s, where the trail's cycle would say 3.
    reps = effective_repetitions_for_duration(
        routes=[RING],
        step_duration_s=1.0,
        repeat_duration_s=30.0,
        lane_left=1,
        lane_right=1,
        lane_frame=LEFT_RIGHT,
        rotation_lock=False,
    )

    assert reps == 2

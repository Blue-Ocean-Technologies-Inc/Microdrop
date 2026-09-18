# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The slug shape as step parameters on the device viewer side (#682): the
sidebar manager carries it, the commit message serialises it with defaults
for older senders, and the geometry message can carry the lattice."""

# Microdrop utils imports.
from microdrop_utils.tests.test_wide_path_slug_phases import square_lattice

# Local imports.
from ..models.messages import GeometryChangedMessage
from ..models.route import RouteLayerManager
from ..models.step_params_commit import StepParamsCommitMessage

STEP_PARAMS = {
    "duration": 1.0,
    "repetitions": 1,
    "repeat_duration": 0,
    "trail_length": 2,
    "trail_overlay": 1,
    "soft_start": False,
    "soft_terminate": False,
    "linear_repeats": False,
}


def test_manager_defaults_to_a_plain_trail_and_round_trips_its_shape():
    manager = RouteLayerManager()
    params = manager._current_params()

    assert (params["lane_left"], params["lane_right"]) == (0, 0)
    assert params["lanes_in_out"] and params["rotation_lock"]

    manager.apply_execution_params(
        {**STEP_PARAMS, "lane_left": 1, "lane_right": 2, "lanes_in_out": False}
    )

    assert (manager.lane_left, manager.lane_right) == (1, 2)
    assert not manager.lanes_in_out and manager.rotation_lock
    assert not manager.commit_enabled


def test_steps_saved_before_the_shape_apply_with_the_plain_trail():
    manager = RouteLayerManager(lane_left=3, lanes_in_out=False)
    manager.apply_execution_params(STEP_PARAMS)

    assert (manager.lane_left, manager.lane_right) == (0, 0)
    assert manager.lanes_in_out and manager.rotation_lock


def test_commit_message_defaults_the_shape_for_older_senders():
    message = StepParamsCommitMessage(step_id="s1", **STEP_PARAMS)
    parsed = StepParamsCommitMessage.deserialize(message.serialize())

    assert (parsed.lane_left, parsed.lane_right) == (0, 0)
    assert parsed.lanes_in_out and parsed.rotation_lock
    assert "lane_left" in parsed.model_dump()


def test_geometry_message_carries_the_lattice_when_given():
    bare = GeometryChangedMessage.deserialize(
        GeometryChangedMessage(id_to_channel={"a": 1}).serialize()
    )
    assert bare.centroids is None and bare.neighbours is None

    full = GeometryChangedMessage(
        id_to_channel={"a": 1, "b": 2},
        centroids={"a": (0.0, 0.0), "b": (1.0, 0.0)},
        neighbours={"a": ["b"], "b": ["a"]},
    )
    parsed = GeometryChangedMessage.deserialize(full.serialize())

    assert parsed.centroids == {"a": (0.0, 0.0), "b": (1.0, 0.0)}
    assert parsed.neighbours == {"a": ["b"], "b": ["a"]}


def test_plan_arguments_spell_out_every_sidebar_setting_once():
    manager = RouteLayerManager(trail_length=2, lane_right=1, lanes_in_out=False)
    arguments = manager.plan_arguments()

    assert arguments["trail_length"] == 2 and arguments["lane_right"] == 1
    assert arguments["lane_frame"] == "left/right" and arguments["rotation_lock"]
    assert set(arguments) == {
        "duration",
        "repetitions",
        "repeat_duration",
        "trail_length",
        "trail_overlay",
        "soft_start",
        "soft_terminate",
        "linear_repeats",
        "lane_left",
        "lane_right",
        "lane_frame",
        "rotation_lock",
    }


def test_slug_footprint_is_every_electrode_the_slug_would_actuate():
    centroids, neighbours, _pitch = square_lattice()
    route = ["e0205", "e0305", "e0405"]
    manager = RouteLayerManager(lane_left=1, lane_right=1, lanes_in_out=False)

    assert manager.slug_footprint([], centroids, neighbours) == set()
    assert manager.slug_footprint(route, centroids, neighbours) == {
        f"e{x:02d}{y:02d}" for x in (2, 3, 4) for y in (4, 5, 6)
    }

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Auto-commit to step (#969): the main model's gate that says when a
sidebar edit is due to be written to the selected step, and its preference."""

# Enthought library imports.
from apptools.preferences.api import Preferences

# Microdrop package imports.
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences

# Local imports.
from .test_route_layer_manager_commit import STEP_VALUES

STEP_B_VALUES = {
    **STEP_VALUES,
    "duration": 0.5,
    "trail_length": 4,
    "lane_left": 0,
    "lane_right": 2,
    "rotation_lock": True,
}

# A step saved before #682 carries none of the slug-shape keys.
PRE_SLUG_SHAPE_STEP_VALUES = {
    name: STEP_B_VALUES[name]
    for name in (
        "duration",
        "repetitions",
        "repeat_duration",
        "trail_length",
        "trail_overlay",
        "soft_start",
        "soft_terminate",
        "linear_repeats",
    )
}


def _model(**preferences):
    helper = DeviceViewerPreferences(preferences=Preferences())
    helper.trait_set(**preferences)

    return DeviceViewMainModel(preferences=helper)


def _select_step(model, step_id, values):
    """Load a step the way the dock pane does: step id, then its values."""
    model.step_id = step_id
    model.routes.apply_execution_params(values)


def test_auto_commit_is_on_by_default_and_saved_to_preferences():
    model = _model()

    assert model.auto_commit_to_step is True

    model.auto_commit_to_step = False

    assert model.preferences.auto_commit_to_step is False


def test_auto_commit_follows_the_saved_preference():
    assert _model(auto_commit_to_step=False).auto_commit_to_step is False


def test_an_edit_on_the_selected_step_is_due():
    model = _model()
    _select_step(model, "a", STEP_VALUES)

    assert model.auto_commit_due is False

    model.routes.lane_left = 2

    assert model.auto_commit_due is True


def test_every_edit_renotifies_so_the_debounce_restarts():
    model = _model()
    _select_step(model, "a", STEP_VALUES)
    events = []
    model.observe(events.append, "auto_commit_due")

    model.routes.duration = 3.0
    model.routes.duration = 3.5

    assert [event.new for event in events] == [True, True]


def test_nothing_is_due_without_a_selected_step():
    model = _model()
    model.routes.apply_execution_params(STEP_VALUES)
    model.routes.lane_left = 2

    assert model.routes.commit_enabled is True
    assert model.auto_commit_due is False


def test_nothing_is_due_while_a_protocol_runs():
    model = _model()
    _select_step(model, "a", STEP_VALUES)
    model.protocol_running = True
    model.routes.lane_left = 2

    assert model.auto_commit_due is False

    model.protocol_running = False

    assert model.auto_commit_due is True


def test_nothing_is_due_with_auto_commit_off():
    model = _model(auto_commit_to_step=False)
    _select_step(model, "a", STEP_VALUES)
    model.routes.lane_left = 2

    assert model.routes.commit_enabled is True
    assert model.auto_commit_due is False


def test_a_commit_clears_the_gate():
    model = _model()
    _select_step(model, "a", STEP_VALUES)
    model.routes.lane_left = 2
    model.routes.mark_params_committed()

    assert model.auto_commit_due is False


def test_selecting_a_step_is_not_an_edit():
    model = _model()
    _select_step(model, "a", STEP_VALUES)
    _select_step(model, "b", STEP_B_VALUES)

    assert model.auto_commit_due is False


def test_an_uncommitted_edit_never_leaks_into_the_next_step():
    model = _model()
    _select_step(model, "a", STEP_VALUES)
    model.routes.lane_left = 2
    model.routes.recentre = True

    _select_step(model, "b", STEP_B_VALUES)

    assert model.routes._current_params() == STEP_B_VALUES
    assert model.auto_commit_due is False


def test_a_step_saved_before_the_slug_shape_resets_it():
    model = _model()
    _select_step(model, "a", STEP_VALUES)
    model.routes.lane_left = 2

    _select_step(model, "b", PRE_SLUG_SHAPE_STEP_VALUES)

    params = model.routes._current_params()

    assert (params["lane_left"], params["lane_right"]) == (0, 0)
    assert params["lanes_in_out"] and params["rotation_lock"] and params["recentre"]
    assert model.auto_commit_due is False


# ------------------------- Commit to Step button -------------------------


def _press(model):
    """Press the button; returns whether the press asked for a commit."""
    requests = []
    model.observe(requests.append, "commit_requested")
    model.routes.commit_to_step_btn = True
    model.observe(requests.append, "commit_requested", remove=True)

    return bool(requests)


def test_the_button_is_unavailable_without_a_step_and_a_press_does_nothing():
    model = _model()

    assert model.commit_button_state == "unavailable"
    assert _press(model) is False
    assert model.auto_commit_to_step is True


def test_auto_state_press_turns_auto_commit_off():
    model = _model()
    _select_step(model, "a", STEP_VALUES)

    assert model.commit_button_state == "auto"
    assert _press(model) is False
    assert model.auto_commit_to_step is False
    assert model.commit_button_state == "idle"


def test_auto_off_press_while_edits_wait_hands_them_back_as_pending():
    model = _model()
    _select_step(model, "a", STEP_VALUES)
    model.routes.lane_left = 2

    _press(model)

    assert model.commit_button_state == "pending"
    assert model.auto_commit_due is False


def test_pending_state_press_commits_and_keeps_auto_commit_off():
    model = _model(auto_commit_to_step=False)
    _select_step(model, "a", STEP_VALUES)
    model.routes.lane_right = 2

    assert model.commit_button_state == "pending"
    assert _press(model) is True
    assert model.auto_commit_to_step is False


def test_idle_state_press_turns_auto_commit_on():
    model = _model(auto_commit_to_step=False)
    _select_step(model, "a", STEP_VALUES)

    assert model.commit_button_state == "idle"
    assert _press(model) is False
    assert model.auto_commit_to_step is True
    assert model.commit_button_state == "auto"


def test_the_state_follows_edits_and_commits():
    model = _model(auto_commit_to_step=False)
    _select_step(model, "a", STEP_VALUES)
    states = []
    model.observe(lambda event: states.append(event.new), "commit_button_state")

    model.routes.duration = 3.0
    model.routes.mark_params_committed()

    assert states == ["pending", "idle"]

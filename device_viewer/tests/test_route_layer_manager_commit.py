# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.consts import STEP_PARAM_NAMES
from device_viewer.models.route import RouteLayerManager

EXEC_PARAMS = {
    "duration": 1.5,
    "repetitions": 3,
    "repeat_duration": 0,
    "trail_length": 2,
    "trail_overlay": 1,
    "soft_start": True,
    "soft_terminate": False,
    "linear_repeats": False,
}


def _apply(mgr, params):
    mgr.apply_execution_params(params)


def test_commit_disabled_when_no_baseline():
    mgr = RouteLayerManager()
    assert mgr.commit_enabled is False


def test_commit_disabled_when_equal_to_baseline():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    assert mgr.commit_enabled is False


def test_commit_enabled_when_any_param_diverges():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    mgr.duration = 5.0
    assert mgr.commit_enabled is True


def test_commit_enabled_resets_after_rebaseline():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    mgr.duration = 5.0
    assert mgr.commit_enabled is True

    # Re-baseline to current values (what commit handler does)
    mgr.mark_params_committed()
    assert mgr.commit_enabled is False


# Every setting a step stores, each off its default so a load that skips one
# shows. Keyed exactly by STEP_PARAM_NAMES: a setting added to the commit
# message fails test_step_values_cover_every_setting until it is added here.
STEP_VALUES = {
    "duration": 2.5,
    "repetitions": 3,
    "repeat_duration": 4,
    "trail_length": 3,
    "trail_overlay": 1,
    "soft_start": True,
    "soft_terminate": True,
    "linear_repeats": True,
    "lane_left": 1,
    "lane_right": 1,
    "lanes_in_out": False,
    "rotation_lock": False,
    "recentre": False,
}


def _changed(value):
    if isinstance(value, bool):
        return not value

    return value + 1


def test_step_values_cover_every_setting():
    assert set(STEP_VALUES) == set(STEP_PARAM_NAMES)


def test_every_setting_is_a_sidebar_trait():
    mgr = RouteLayerManager()

    assert all(mgr.trait(name) is not None for name in STEP_PARAM_NAMES)


def test_loading_a_step_sets_every_setting():
    mgr = RouteLayerManager()
    _apply(mgr, STEP_VALUES)

    assert mgr._current_params() == STEP_VALUES
    assert mgr.commit_enabled is False


@pytest.mark.parametrize("name", STEP_PARAM_NAMES)
def test_every_setting_enables_and_notifies_commit(name):
    """The view's enabled_when only re-evaluates on a notification, so a
    setting that changes the value without one leaves the button stale —
    the lane widths did (#969)."""
    mgr = RouteLayerManager()
    _apply(mgr, STEP_VALUES)
    events = []
    mgr.observe(events.append, "commit_enabled")

    setattr(mgr, name, _changed(STEP_VALUES[name]))

    assert mgr.commit_enabled is True
    assert events and events[-1].new is True


def test_returning_to_the_step_values_disables_commit():
    mgr = RouteLayerManager()
    _apply(mgr, STEP_VALUES)
    events = []
    mgr.observe(events.append, "commit_enabled")

    mgr.lane_right = 2
    mgr.lane_right = 1

    assert [event.new for event in events] == [True, False]

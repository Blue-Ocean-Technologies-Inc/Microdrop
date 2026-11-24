# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Contract tests for the heater verify topics: request bounds and defaults,
the done payload (refusal and outcome), and the publisher/topic pairing.
Hardware-free, no Redis, no vendor driver."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    HEATER_TUNE_DEFAULT_MAX_TEMP_C,
    HEATER_TUNE_MARGIN_C,
    HEATER_TUNE_MAX_TEMP_C_BOUNDS,
    HEATER_TUNE_VERIFY_DEFAULT_BAND_C,
    HEATER_TUNE_VERIFY_DEFAULT_HOLD_S,
    HEATER_TUNE_VERIFY_DONE,
    HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS,
    HEATER_TUNE_VERIFY_START,
    HeaterTuneProgress,
    HeaterTuneVerifyDone,
    HeaterTuneVerifyStartRequest,
    heater_tune_verify_done_publisher,
    heater_tune_verify_start_publisher,
)


def test_a_verify_request_fills_the_vendor_defaults():
    request = HeaterTuneVerifyStartRequest(channel=1, setpoint_c=42.5)

    assert request.max_temp_c == HEATER_TUNE_DEFAULT_MAX_TEMP_C
    assert request.band_c == HEATER_TUNE_VERIFY_DEFAULT_BAND_C
    assert request.hold_s == HEATER_TUNE_VERIFY_DEFAULT_HOLD_S


def test_the_set_point_ceiling_is_the_cap_ceiling_minus_the_margin():
    ceiling_c = HEATER_TUNE_MAX_TEMP_C_BOUNDS[1] - HEATER_TUNE_MARGIN_C

    assert HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS[1] == ceiling_c


@pytest.mark.parametrize(
    "change",
    [
        {"channel": 2},
        {"setpoint_c": HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS[1] + 0.5},
        {"max_temp_c": 95.0},
        {"max_duration_s": 10},
        {"band_c": 0.0},
        {"hold_s": -1},
    ],
)
def test_a_verify_request_out_of_bounds_is_rejected(change):
    with pytest.raises(ValidationError):
        HeaterTuneVerifyStartRequest(**{"channel": 0, "setpoint_c": 40.0, **change})


def test_a_refusal_needs_no_metrics():
    done = HeaterTuneVerifyDone(channel=0, ok=False, reason="ch1 is on")

    assert done.metrics is None and done.off_confirmed


def test_an_outcome_carries_the_step_metrics():
    done = HeaterTuneVerifyDone.model_validate(
        {
            "channel": 0,
            "ok": True,
            "reason": "time limit",
            "setpoint_c": 40.0,
            "band_c": 0.5,
            "metrics": {
                "dead_time_s": 2.0,
                "rise_s": None,
                "peak_c": 40.3,
                "overshoot_pct": 2.0,
                "settle_s": None,
                "sse_c": -0.2,
                "settled": False,
                "duration_s": 600.0,
            },
        }
    )

    assert done.metrics.rise_s is None and done.metrics.peak_c == 40.3


def test_a_capture_progress_has_no_set_point():
    progress = HeaterTuneProgress(channel=0, phase="step", elapsed_s=12.0)

    assert progress.setpoint_c is None


def test_the_publishers_pair_with_their_topics():
    assert heater_tune_verify_start_publisher.topic == HEATER_TUNE_VERIFY_START
    assert heater_tune_verify_done_publisher.topic == HEATER_TUNE_VERIFY_DONE

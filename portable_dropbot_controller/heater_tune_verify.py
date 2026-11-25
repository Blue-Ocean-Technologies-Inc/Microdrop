# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The heater verify run, as the vendor's tuning panel drives
``dropbot_portable.heater_tune.VerifyRun``: a set point and the regulated
loop on the board's own gains (TEMP_SET_TARGET + TEMP_START_STOP 1), one
reading a second until the reading has held the band, the time limit, the
cap or a sensor outage, then the heater off and the response figures
(``step_metrics``). The loop and its safety are the capture's
(``heater_tune_capture.run_heater_machine``)."""

# Standard library imports.
import time

# Third-party imports.
from dropbot_portable.heater_tune import VerifyConfig, VerifyRun

# Local imports.
from .consts import HEATER_TUNE_SAMPLE_INTERVAL_S
from .heater_tune_capture import run_heater_machine


def run_verify(
    board,
    config,
    cancel,
    publish_progress,
    clock=time.monotonic,
    interval_s=HEATER_TUNE_SAMPLE_INTERVAL_S,
):
    """Run one verify on ``board``: the set point and the loop start, then
    the readings. Returns ``(run, off_confirmed)`` as ``run_heater_machine``
    does."""
    run = VerifyRun(config, t0=clock())

    return run_heater_machine(
        board,
        run,
        cancel,
        publish_progress,
        clock=clock,
        interval_s=interval_s,
        first_commands=run.start(),
    )


def verify_config(request):
    """The vendor VerifyConfig for a validated HeaterTuneVerifyStartRequest
    (its margin keeps the vendor panel's default)."""

    return VerifyConfig(
        channel=request.channel,
        setpoint_c=request.setpoint_c,
        max_temp_c=request.max_temp_c,
        max_duration_s=float(request.max_duration_s),
        band_c=request.band_c,
        hold_s=float(request.hold_s),
    )


def summarize_verify(run):
    """The HeaterTuneVerifyDone fields of a finished run: ``ok`` once it ran
    to its end (settled or the time limit), with the metrics of whatever it
    recorded, an aborted run's too."""
    config = run.cfg
    outcome = {
        "channel": config.channel,
        "ok": run.phase == "done",
        "reason": run.reason,
        "setpoint_c": config.setpoint_c,
        "band_c": config.band_c,
    }

    if len(run.samples) < 2:
        return outcome

    metrics = run.metrics()
    metrics.pop("reason", None)

    return {**outcome, "metrics": metrics}

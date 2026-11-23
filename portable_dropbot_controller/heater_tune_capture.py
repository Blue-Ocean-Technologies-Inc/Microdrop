# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The heater auto-tune run, as the vendor's tuning panel drives
``dropbot_portable.heater_tune``: read the heater once a second, feed the
``StepCapture`` state machine, send the commands it returns, then fit and
propose. GUI- and controller-free: the board is any object with the
``HeaterTuneBoard`` methods (``attached``, ``read``, ``drive``, ``off``).

Safety, on top of the state machine's own (never past the cap, bounded
duration, abort on missing or outage readings): a refused drive aborts the
run, OFF is resent until acknowledged, and whatever ends the run (cancel,
error, an exception) the heater is switched off once more unless an OFF was
already confirmed. A lost link cannot send anything: the firmware's
host-silence failsafe (alarm 09004) cuts the heater then."""

# Standard library imports.
import threading
import time

# Third-party imports.
from dropbot_portable.heater_tune import (
    CMD_DONE,
    CMD_DRIVE,
    CMD_OFF,
    CaptureConfig,
    StepCapture,
    smith_model,
    tune_pid,
)
from dropbot_portable.param_layout import TEMP_SMITH_DEFAULT, temp_smith_problem

# Local imports.
from .consts import (
    HEATER_TUNE_OFF_ATTEMPTS,
    HEATER_TUNE_SAMPLE_INTERVAL_S,
    HEATER_TUNE_STYLES,
)

#: Why a run ended on a lost link: nothing can be sent any more.
CONNECTION_LOST_REASON = (
    "connection lost: the heater could not be switched off from here; the "
    "firmware host-silence failsafe (alarm 09004) cuts it"
)
#: The run's phase while the fit runs (after the capture, heater off).
FITTING_PHASE = "fitting"


class HeaterTuneCancel(threading.Event):
    """The run's cancel event, carrying why it was cancelled; the first
    reason wins."""

    reason = ""

    def cancel(self, reason):
        if not self.is_set():
            self.reason = reason

        self.set()


def run_step_capture(
    board,
    config,
    cancel,
    publish_progress,
    clock=time.monotonic,
    interval_s=HEATER_TUNE_SAMPLE_INTERVAL_S,
):
    """Run one step capture on ``board`` until the state machine is done,
    ``cancel`` is set or the link is lost. Returns ``(capture,
    off_confirmed)``: ``off_confirmed`` is False when the heater may still
    be driven (OFF never acknowledged, or the link was lost meanwhile)."""
    capture = StepCapture(config, t0=clock())
    state = {"driven": False}

    try:
        while capture.active:
            if cancel.wait(interval_s):
                _execute(board, capture, capture.abort(cancel.reason), state)

                break

            if not board.attached():
                capture.abort(CONNECTION_LOST_REASON)

                break

            current_c, output_pct = board.read(config.channel) or (None, None)
            commands = capture.feed(clock(), current_c, output_pct)
            publish_progress(capture, current_c)
            _execute(board, capture, commands, state)
    finally:
        if state["driven"] and board.attached():
            _switch_off(board, config.channel, state)

    return capture, not state["driven"]


def _execute(board, capture, commands, state):
    """Send the state machine's commands; a refused drive aborts the run
    (its OFF is sent right after)."""
    channel = capture.cfg.channel

    for command in commands:
        if command[0] == CMD_DRIVE:
            state["driven"] = True

            if not board.drive(channel, int(command[1])):
                _execute(board, capture, capture.abort("drive refused"), state)

                return

        elif command[0] == CMD_OFF and board.attached():
            _switch_off(board, channel, state)

        elif command[0] == CMD_DONE:
            return


def _switch_off(board, channel, state):
    """Send OFF until acknowledged, at most HEATER_TUNE_OFF_ATTEMPTS
    times; a confirmed OFF clears ``state["driven"]``."""

    for _attempt in range(HEATER_TUNE_OFF_ATTEMPTS):
        if board.off(channel):
            state["driven"] = False

            return True

    return False


def summarize_capture(capture):
    """The HeaterTuneDone fields of a finished capture: the fit, a proposal
    per tuning style and the Smith model row, or ``ok`` False and why."""
    channel = capture.cfg.channel

    if capture.phase == "aborted" or capture.t_step is None:
        return {"channel": channel, "ok": False, "reason": capture.reason}

    try:
        fit = capture.fit()
        tunings = {style: tune_pid(fit, style) for style in HEATER_TUNE_STYLES}
    except ValueError as error:
        return {"channel": channel, "ok": False, "reason": f"no usable fit: {error}"}

    model, model_notes = smith_model(fit)
    proposals = {
        style: {
            "kp": tuning.kp,
            "ki": tuning.ki,
            "kd": tuning.kd,
            "lambda_s": tuning.lam,
            "notes": list(tuning.notes),
        }
        for style, tuning in tunings.items()
    }

    return {
        "channel": channel,
        "ok": True,
        "reason": capture.reason,
        "fit": {
            "gain": fit.gain,
            "tau_s": fit.tau,
            "dead_time_s": fit.dead_time,
            "r2": fit.r2,
            "rmse_c": fit.rmse,
            "reached": fit.reached,
        },
        "proposals": proposals,
        "smith_model": model,
        "notes": list(fit.notes) + list(model_notes),
    }


def capture_config(request):
    """The vendor CaptureConfig for a validated HeaterTuneStartRequest (the
    other fields keep the vendor panel's defaults)."""

    return CaptureConfig(
        channel=request.channel,
        duty_pct=request.duty_pct,
        max_temp_c=request.max_temp_c,
        max_duration_s=float(request.max_duration_s),
    )


def smith_model_refusal(channel, smith_model_row):
    """Why the MCU would refuse this channel's Smith model row, or "". The
    other channel's row is checked with the compiled default in its place:
    apply_tuning keeps the board's own row there."""
    rows = [tuple(row) for row in TEMP_SMITH_DEFAULT]
    rows[channel] = tuple(smith_model_row)

    return temp_smith_problem(rows) or ""

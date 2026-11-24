# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater auto-tune (dropbot-portable 1.8.0 ``heater_tune``): the bounds the
vendor's tuning panel offers, and the start / progress / done / apply /
verify message contracts. A tune is an open-loop duty step on one heater
(10 s baseline, the step until a plateau, the cap or the time limit, then
30 s of cool-down), a first-order-plus-dead-time fit, and proposed PI gains
plus the Smith predictor model (``temp_smith``), written only on an explicit
apply. A verify run then regulates to a set point on the board's own loop
(the gains it holds) and reports the response (``step_metrics``)."""

# Third-party imports.
from pydantic import BaseModel, Field

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Local imports.
from .heater import TEMP_CHANNEL_MAX, TempSetPidRequest
from .topics import (
    HEATER_TUNE_APPLIED,
    HEATER_TUNE_APPLY,
    HEATER_TUNE_DONE,
    HEATER_TUNE_PROGRESS,
    HEATER_TUNE_START,
    HEATER_TUNE_VERIFY_DONE,
    HEATER_TUNE_VERIFY_START,
)

#: The vendor panel's step duty spin box (TEMP_HEAT_PWM %).
HEATER_TUNE_DUTY_PCT_BOUNDS = (1, 100)
HEATER_TUNE_DEFAULT_DUTY_PCT = 20
#: The temperature the step never heats past (heater_tune.CAP_RANGE_C);
#: the backend also holds it below the board's max_temp_c minus
#: TEMP_TARGET_MAX_MARGIN_C, the MCU's own target ceiling.
HEATER_TUNE_MAX_TEMP_C_BOUNDS = (30.0, 90.0)
HEATER_TUNE_DEFAULT_MAX_TEMP_C = 50.0
#: Time limit of the heating phase (s), the vendor panel's bounds.
HEATER_TUNE_DURATION_S_BOUNDS = (30, 3600)
HEATER_TUNE_DEFAULT_DURATION_S = 600
#: Closed-loop speed of the proposed gains (heater_tune.TUNING_STYLES):
#: smooth is the slowest with the widest margin, fast the quickest.
HEATER_TUNE_STYLES = ("smooth", "default", "fast")
HEATER_TUNE_DEFAULT_STYLE = "default"
#: The loop period the proposed gains are designed for and written with
#: (heater_tune.tune_pid's 1 s control period, apply_tuning's 1000 ms).
HEATER_TUNE_PERIOD_MS = 1000
#: HeaterTuneProgress.phase once the capture is over (heater off) and its
#: response is being fitted; the capture's own phases are the vendor
#: StepCapture's (baseline, step, cooldown).
HEATER_TUNE_FITTING_PHASE = "fitting"
#: The vendor panel reads the heater once a second (TEMP_READ_INFO).
HEATER_TUNE_SAMPLE_INTERVAL_S = 1.0
#: Heater OFF is sent this many times before the run reports it as not
#: confirmed (the vendor panel's first send plus OFF_RETRIES).
HEATER_TUNE_OFF_ATTEMPTS = 3
#: How long plugin stop waits for a cancelled tune to switch its heater off.
HEATER_TUNE_JOIN_TIMEOUT_S = 10.0
#: How far below the cap a run keeps the heater (the vendor CaptureConfig /
#: VerifyConfig margin_c): heating stops, and a set point must stay, there.
HEATER_TUNE_MARGIN_C = 1.5
#: HeaterTuneProgress.phase of a verify run (the vendor VerifyRun's
#: "running").
HEATER_TUNE_VERIFY_PHASE = "verify"
#: The verify run's set point; it must also sit at least 1 °C above the
#: current reading and HEATER_TUNE_MARGIN_C below the run's cap
#: (heater_tune.verify_problem).
HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS = (
    20.0,
    HEATER_TUNE_MAX_TEMP_C_BOUNDS[1] - HEATER_TUNE_MARGIN_C,
)
HEATER_TUNE_VERIFY_DEFAULT_SETPOINT_C = 40.0
#: The settling band around the set point (°C) and how long the reading must
#: stay in it to end the run early (s); defaults are the vendor VerifyConfig's.
HEATER_TUNE_VERIFY_BAND_C_BOUNDS = (0.1, 5.0)
HEATER_TUNE_VERIFY_DEFAULT_BAND_C = 0.5
HEATER_TUNE_VERIFY_HOLD_S_BOUNDS = (0, 600)
HEATER_TUNE_VERIFY_DEFAULT_HOLD_S = 60

# --------------------------------------------------------------------- #
# Heater auto-tune message contracts (topic + schema, one unit)          #
# --------------------------------------------------------------------- #


class HeaterTuneStartRequest(BaseModel):
    """Start a step capture on one heater; both heaters must be off."""

    channel: int = Field(ge=0, le=TEMP_CHANNEL_MAX)
    duty_pct: int = Field(
        HEATER_TUNE_DEFAULT_DUTY_PCT,
        ge=HEATER_TUNE_DUTY_PCT_BOUNDS[0],
        le=HEATER_TUNE_DUTY_PCT_BOUNDS[1],
    )
    max_temp_c: float = Field(
        HEATER_TUNE_DEFAULT_MAX_TEMP_C,
        ge=HEATER_TUNE_MAX_TEMP_C_BOUNDS[0],
        le=HEATER_TUNE_MAX_TEMP_C_BOUNDS[1],
    )
    max_duration_s: int = Field(
        HEATER_TUNE_DEFAULT_DURATION_S,
        ge=HEATER_TUNE_DURATION_S_BOUNDS[0],
        le=HEATER_TUNE_DURATION_S_BOUNDS[1],
    )


class HeaterTuneProgress(BaseModel):
    """One reading of a running capture or verify run: its phase (baseline,
    step, cooldown, fitting, verify), the time since it started, and the
    duty driven (during a verify run, the loop output the board reports)."""

    channel: int
    phase: str
    elapsed_s: float
    current_c: float | None = None
    duty_pct: int = 0
    #: The verify run's set point; None during a capture.
    setpoint_c: float | None = None


class HeaterTuneFit(BaseModel):
    """The fitted plant: gain (°C per % output), time constant, dead time,
    and the fit quality (R², rms error, fraction of the response covered)."""

    gain: float
    tau_s: float
    dead_time_s: float
    r2: float
    rmse_c: float
    reached: float
    #: The fitted baseline temperature, where the modelled response starts.
    y0_c: float | None = None


class HeaterTuneProposal(BaseModel):
    """PI gains for one tuning style and its closed-loop time constant."""

    kp: float
    ki: float
    kd: float
    lambda_s: float
    notes: list[str] = []


class HeaterTuneDone(BaseModel):
    """A tune's outcome, or its refusal (`ok` false, `reason` why). The
    heater is off by then; `off_confirmed` false means the OFF was never
    acknowledged and the operator must check it."""

    channel: int
    ok: bool
    reason: str = ""
    off_confirmed: bool = True
    fit: HeaterTuneFit | None = None
    proposals: dict[str, HeaterTuneProposal] = {}
    #: The Smith predictor row for this channel: (gain °C/%, tau s, dead s).
    smith_model: tuple[float, float, float] | None = None
    notes: list[str] = []


class HeaterTuneApplyRequest(TempSetPidRequest):
    """Write proposed gains (held to what the firmware accepts, as a manual
    PID set) and this channel's Smith model row; `persist` also presets
    both to flash."""

    period_ms: int = HEATER_TUNE_PERIOD_MS
    smith_model: tuple[float, float, float]
    persist: bool = False


class HeaterTuneApplied(BaseModel):
    """An apply's outcome: gains written, the temp_smith outcome ("ok",
    "not served" by older firmware, or the write failure), and whether the
    gains were persisted (None without persist); `error` for a refusal."""

    channel: int
    gains: bool = False
    smith: str = ""
    gains_persisted: bool | None = None
    error: str = ""


class HeaterTuneVerifyStartRequest(BaseModel):
    """Regulate one heater to a set point with the gains the board holds
    (typically right after an apply); both heaters must be off."""

    channel: int = Field(ge=0, le=TEMP_CHANNEL_MAX)
    setpoint_c: float = Field(
        HEATER_TUNE_VERIFY_DEFAULT_SETPOINT_C,
        ge=HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS[0],
        le=HEATER_TUNE_VERIFY_SETPOINT_C_BOUNDS[1],
    )
    max_temp_c: float = Field(
        HEATER_TUNE_DEFAULT_MAX_TEMP_C,
        ge=HEATER_TUNE_MAX_TEMP_C_BOUNDS[0],
        le=HEATER_TUNE_MAX_TEMP_C_BOUNDS[1],
    )
    max_duration_s: int = Field(
        HEATER_TUNE_DEFAULT_DURATION_S,
        ge=HEATER_TUNE_DURATION_S_BOUNDS[0],
        le=HEATER_TUNE_DURATION_S_BOUNDS[1],
    )
    band_c: float = Field(
        HEATER_TUNE_VERIFY_DEFAULT_BAND_C,
        ge=HEATER_TUNE_VERIFY_BAND_C_BOUNDS[0],
        le=HEATER_TUNE_VERIFY_BAND_C_BOUNDS[1],
    )
    hold_s: int = Field(
        HEATER_TUNE_VERIFY_DEFAULT_HOLD_S,
        ge=HEATER_TUNE_VERIFY_HOLD_S_BOUNDS[0],
        le=HEATER_TUNE_VERIFY_HOLD_S_BOUNDS[1],
    )


class HeaterTuneVerifyMetrics(BaseModel):
    """The set-point response from the loop start (heater_tune.step_metrics):
    dead time, 10-90 % rise, peak, overshoot (% of the step), settling time
    (last exit from the band), steady-state error (mean over the last 30 s);
    None where the record does not show it."""

    dead_time_s: float | None = None
    rise_s: float | None = None
    peak_c: float | None = None
    overshoot_pct: float | None = None
    settle_s: float | None = None
    sse_c: float | None = None
    settled: bool = False
    duration_s: float | None = None


class HeaterTuneVerifyDone(BaseModel):
    """A verify run's outcome, or its refusal (`ok` false, `reason` why). An
    aborted run still carries the metrics of what it recorded. The heater is
    off by then; `off_confirmed` false means the OFF was never acknowledged
    and the operator must check it."""

    channel: int
    ok: bool
    reason: str = ""
    off_confirmed: bool = True
    setpoint_c: float | None = None
    band_c: float | None = None
    metrics: HeaterTuneVerifyMetrics | None = None


heater_tune_start_publisher = ValidatedTopicPublisher(
    topic=HEATER_TUNE_START, validator_class=HeaterTuneStartRequest
)
heater_tune_progress_publisher = ValidatedTopicPublisher(
    topic=HEATER_TUNE_PROGRESS, validator_class=HeaterTuneProgress
)
heater_tune_done_publisher = ValidatedTopicPublisher(
    topic=HEATER_TUNE_DONE, validator_class=HeaterTuneDone
)
heater_tune_apply_publisher = ValidatedTopicPublisher(
    topic=HEATER_TUNE_APPLY, validator_class=HeaterTuneApplyRequest
)
heater_tune_applied_publisher = ValidatedTopicPublisher(
    topic=HEATER_TUNE_APPLIED, validator_class=HeaterTuneApplied
)
heater_tune_verify_start_publisher = ValidatedTopicPublisher(
    topic=HEATER_TUNE_VERIFY_START, validator_class=HeaterTuneVerifyStartRequest
)
heater_tune_verify_done_publisher = ValidatedTopicPublisher(
    topic=HEATER_TUNE_VERIFY_DONE, validator_class=HeaterTuneVerifyDone
)

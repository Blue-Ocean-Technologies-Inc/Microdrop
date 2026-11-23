# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Portable DropBot self-test hub's message contract.

This plugin is the frontend (Tools > Self Tests... opens the hub panel);
the HANDLER of every request below is the portable backend,
``portable_dropbot_controller``'s self-test mixin service, which imports
this module (consts-only, allowed by ``.importlinter``). The contract lives
here rather than in the controller's consts so that file stops growing.

Keep this module free of Qt, TraitsUI and vendor (``dropbot_portable``)
imports: the headless backend imports it. Both sides take the test
catalogue (names, titles, pad needs, repeat parameters) from
``dropbot_portable.self_test`` directly, imported lazily.

Behaviour both sides rely on
----------------------------

Runs and ``run_id``
    The frontend mints a ``run_id`` for every run request. Every progress,
    result and finished message carries it, and the frontend ignores
    messages for any run_id but the one it is tracking (a second frontend
    or a stale message must not corrupt its model).

Message order
    For every ``self_test_run`` request the backend publishes EXACTLY ONE
    ``self_test_finished``, always last. A refused run publishes only that
    finished message, with ``refused_reason`` set. An accepted run
    publishes, per test, ``self_test_progress`` (start, steps, done) then
    one ``self_test_result``, interleaved with ``phase="choreography"``
    progress for the HV-off / pad moves between tests and the restore.

Refusals
    A run is refused (before any HV change or pad move) when: a run is
    already in progress; a PMT or fluorescence session holds the board;
    realtime mode is on or a protocol is running; Home All or a smart chip
    lock / unlock is running; a test name is not in
    ``ALL_TESTS`` or ``HEALTH_TESTS`` or a ``test_kwargs`` key is not a
    known parameter of its test; the pads' state is unknown and a selected
    test needs them moved;
    the tray does not read where the run wants it (``tray_in``, forced IN
    by ``tray_in_required``); or the backend's own chip read at run start
    detects no board and ``chip_absent_acknowledged`` is False. Preflight
    reads and calibration saves report a refusal or failure in their
    reply's ``error``.

Exclusive board ownership
    While a run is in progress the backend refuses every other
    ``portable_dropbot/requests/*`` topic except abort, preflight read and
    the motor E-STOP (``portable_dropbot/requests/motor_estop``; the
    connection requests that are no-ops while connected also pass), with a
    logged warning. A disconnect request during a run is turned into an
    abort: the port is never closed under a running test, whose restore
    must still reach the board to switch HV off.

E-STOP
    An E-STOP during a run halts it, as the vendor runner does: the test
    stops at its next step, the restore switches HV off and no pad move is
    sent afterwards (the restore note says why). The finished message is
    ``cancelled`` with ``error`` naming the E-STOP.

Health tests
    The vendor's ``HEALTH_TESTS`` run like the others (after them in Run
    all). ``test_motors`` needs the tray IN, and its ``moves`` (PMT-Y and
    the filter go out and back) is confirmed by the operator first.
    ``test_heaters``' heat step drives each OFF heater and switches it off
    again on every path of its own, cancel and E-STOP included; while it
    runs, a disconnect or the backend's teardown also switches both heaters
    off (the vendor worker's ``shutdown_heaters``).

Verdicts and titles
    Computed by the backend (``self_test.verdicts`` and the vendor titles),
    so every frontend shows the same judgement.

Unsaved calibration
    The feedback-cap calibration and the electrode tare the tests capture
    live in the board's RAM only until saved. ``unsaved`` is backend-owned
    state: set when a run leaves either captured-but-unsaved, cleared by a
    successful ``self_test_save_calibration`` and on disconnect, and
    reported on finished, preflight and save replies.

Results and reports
    ``self_test_result.result`` is the vendor result made JSON-safe
    (``_to_jsonable``: arrays to lists, NaN to None). The backend also
    writes each test's JSON under the experiment directory and reports the
    path for reference only; the frontend regenerates any report (Markdown
    or HTML) locally from the inline results, so a remote frontend works.
"""

# Standard library imports.
from typing import Literal

# Third-party imports.
from pydantic import BaseModel, Field

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Labels of the RAM-only calibration parts a run can leave unsaved.
UNSAVED_CALIBRATION = "calibration"
UNSAVED_TARE = "tare"
UNSAVED_PARTS = (UNSAVED_CALIBRATION, UNSAVED_TARE)

#: Preflight reply ``error`` while another step holds the board; the
#: frontend keeps its last checklist and polls again.
PREFLIGHT_BOARD_BUSY_ERROR = "board busy"

#: Tests that need the tray IN (the vendor pre-flight's TRAY_IN_TESTS: the
#: motor test moves PMT-Y, and the PMT / magnet interlocks want the tray
#: inside). Every other test runs with the tray in or out.
TRAY_IN_TESTS = ("test_motors",)


def tray_in_required(tests, run_all=False):
    """Whether a run of ``tests`` must have the tray IN: Run all always
    does, as does any run of a TRAY_IN_TESTS test (vendor rule)."""
    return bool(run_all) or any(name in TRAY_IN_TESTS for name in tests)


# --------------------------------------------------------------------- #
# Topics                                                                 #
# --------------------------------------------------------------------- #

# Requests (frontend -> portable backend). Flat names: the backend
# dispatches on the last topic segment (on_<segment>_request).
SELF_TEST_RUN = "portable_dropbot/requests/self_test_run"
SELF_TEST_ABORT = "portable_dropbot/requests/self_test_abort"
#: Empty message; answered on SELF_TEST_PREFLIGHT_UPDATED.
SELF_TEST_PREFLIGHT_READ = "portable_dropbot/requests/self_test_preflight_read"
SELF_TEST_SAVE_CALIBRATION = "portable_dropbot/requests/self_test_save_calibration"

# Signals (portable backend -> frontend).
SELF_TEST_PREFLIGHT_UPDATED = "portable_dropbot/signals/self_test_preflight_updated"
SELF_TEST_PROGRESS = "portable_dropbot/signals/self_test_progress"
SELF_TEST_RESULT = "portable_dropbot/signals/self_test_result"
SELF_TEST_FINISHED = "portable_dropbot/signals/self_test_finished"
SELF_TEST_CALIBRATION_SAVED = "portable_dropbot/signals/self_test_calibration_saved"

#: The hub's plugin-lifetime listener (the model outlives the panel, so
#: reopening it mid-run or after a run still shows the state).
SELF_TEST_LISTENER = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    SELF_TEST_LISTENER: [
        SELF_TEST_PREFLIGHT_UPDATED,
        SELF_TEST_PROGRESS,
        SELF_TEST_RESULT,
        SELF_TEST_FINISHED,
        SELF_TEST_CALIBRATION_SAVED,
    ]
}

# --------------------------------------------------------------------- #
# Message schemas                                                        #
# --------------------------------------------------------------------- #


class SelfTestRunRequest(BaseModel):
    """Run the listed tests in this order."""

    run_id: str = Field(min_length=1)
    #: Names from the vendor's ``ALL_TESTS`` and ``HEALTH_TESTS``;
    #: validated by the backend.
    tests: list[str] = Field(min_length=1)
    #: Per-test keyword overrides, e.g. ``{"test_voltage": {"n": 5},
    #: "test_channels": {"n_reps": 3, "threshold_pf": 5.0},
    #: "test_motors": {"moves": False}}``.
    test_kwargs: dict[str, dict[str, float | int | bool]] = {}
    #: The operator confirmed starting without a detected test board.
    chip_absent_acknowledged: bool = False
    #: Started by Run all, which always runs with the tray IN.
    run_all: bool = False
    #: The tray position the operator chose (True = in); overridden to IN
    #: when ``tray_in_required`` says so. The run refuses when the tray
    #: reads elsewhere.
    tray_in: bool = True


class SelfTestAbortRequest(BaseModel):
    """Stop the running test at its next step; the restore still runs."""

    #: Empty aborts whatever run is in progress.
    run_id: str = ""


class SelfTestSaveCalibrationRequest(BaseModel):
    """Write the RAM-only calibration parts a run captured to flash."""

    calibration: bool = False
    tare: bool = False


class SelfTestPreflight(BaseModel):
    """Raw board state for the pre-run checklist, plus the hub's own
    state so a reopened panel can resync. None = could not be read."""

    tray_in: bool | None = None
    pads_pressed: bool | None = None
    #: STATUS chip_on_pad raw mask (bit0 = debounced pad contact, the bit
    #: the HV interlock uses) — not the chip-detect-rule-adjusted value.
    chip_on_pad_mask: int | None = None
    #: STATUS chip_res; the vendor's test-board window is 1200-2200.
    chip_res: int | None = None
    board_detected: bool | None = None
    running: bool = False
    #: The run in progress, empty when idle.
    run_id: str = ""
    unsaved: list[str] = []
    error: str = ""


class SelfTestProgress(BaseModel):
    """Progress of the running run; ``index``/``total`` span the whole
    run, not one test."""

    run_id: str
    #: "choreography" = HV-off / pad move / restore step between tests
    #: (described in ``text``); start/step/done = the vendor test events.
    phase: Literal["choreography", "start", "step", "done"]
    index: int = 0
    total: int = 0
    name: str = ""
    step: int | None = None
    steps: int | None = None
    text: str = ""
    error: bool = False
    cancelled: bool = False


class SelfTestResult(BaseModel):
    """One finished test."""

    run_id: str
    name: str
    title: str
    #: None = the test gives no verdict (info tests, errors, no data).
    verdict: bool | None = None
    duration: float | None = None
    utc_timestamp: str = ""
    error: str = ""
    cancelled: bool = False
    restore_errors: list[str] = []
    #: The vendor result dict, JSON-safe; the traceback goes to the log.
    result: dict = {}
    #: Where the backend saved this test's JSON (reference only).
    results_path: str = ""


class SelfTestFinished(BaseModel):
    """Exactly one per run request, always the run's last message."""

    run_id: str
    #: Set when the run never started; nothing else happened.
    refused_reason: str = ""
    cancelled: bool = False
    #: A failure that ended the run early (e.g. disconnect, pad move).
    error: str = ""
    #: What the restore did, or why it was skipped.
    restore_note: str = ""
    verdicts: dict[str, bool | None] = {}
    unsaved: list[str] = []
    #: The backend folder holding this run's JSON files (reference only).
    directory: str = ""


class SelfTestCalibrationSaved(BaseModel):
    """Outcome of a save-calibration request."""

    #: Firmware status code of the calibration save; None = not attempted.
    calibration_status: int | None = None
    calibration_text: str = ""
    #: None = tare save not attempted.
    tare_ok: bool | None = None
    unsaved: list[str] = []
    error: str = ""


self_test_run_publisher = ValidatedTopicPublisher(
    topic=SELF_TEST_RUN, validator_class=SelfTestRunRequest
)
self_test_abort_publisher = ValidatedTopicPublisher(
    topic=SELF_TEST_ABORT, validator_class=SelfTestAbortRequest
)
self_test_save_calibration_publisher = ValidatedTopicPublisher(
    topic=SELF_TEST_SAVE_CALIBRATION, validator_class=SelfTestSaveCalibrationRequest
)
self_test_preflight_publisher = ValidatedTopicPublisher(
    topic=SELF_TEST_PREFLIGHT_UPDATED, validator_class=SelfTestPreflight
)
self_test_progress_publisher = ValidatedTopicPublisher(
    topic=SELF_TEST_PROGRESS, validator_class=SelfTestProgress
)
self_test_result_publisher = ValidatedTopicPublisher(
    topic=SELF_TEST_RESULT, validator_class=SelfTestResult
)
self_test_finished_publisher = ValidatedTopicPublisher(
    topic=SELF_TEST_FINISHED, validator_class=SelfTestFinished
)
self_test_calibration_saved_publisher = ValidatedTopicPublisher(
    topic=SELF_TEST_CALIBRATION_SAVED, validator_class=SelfTestCalibrationSaved
)

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test hub's state: the test table and its parameters, the run
being tracked and its outputs, and the backend-owned unsaved calibration.
Plugin-lifetime, so a reopened panel shows it all."""

# Standard library imports.
import uuid

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Enum,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
)

# Local imports.
from ..consts import UNSAVED_CALIBRATION, UNSAVED_TARE, tray_in_required
from .consts import (
    CALIBRATION_TEST,
    CHANNELS_TEST,
    OUTCOME_NOT_RUN,
    OUTCOME_QUEUED,
    OUTCOME_RUNNING,
    OUTPUT_VIEW_PLOTS,
    OUTPUT_VIEW_REPORT,
    PADS_LABELS,
    UNSAVED_PART_LABELS,
)
from .preflight_model import PreflightModel
from .run_outputs import SelfTestRunOutputs
from .self_test_parameters import SelfTestParameters
from .self_test_row import SelfTestRow

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class SelfTestHubModel(HasTraits):
    """Qt-free hub state, mutated on the GUI thread only. Messages of any
    run but the tracked ``run_id`` are ignored."""

    #: One row per vendor test, in the vendor tab's order: ``ALL_TESTS``,
    #: then the health tests.
    rows = List(Instance(SelfTestRow))

    #: The test parameters of the next run.
    parameters = Instance(SelfTestParameters, ())

    run_selected_button = Button("Run selected")
    run_all_button = Button("Run all")
    abort_button = Button("Abort self-test")
    save_report_button = Button("Save report")
    save_calibration_button = Button("Save calibration to flash")

    #: Tests waiting on the pre-flight check; empty when none is pending.
    pending_tests = List(Str)

    #: The pending tests came from Run all, which keeps the tray IN.
    pending_run_all = Bool(False)

    #: The pre-run checklist of the pending tests.
    preflight = Instance(PreflightModel, ())

    #: The tracked run. Kept after the run ends, so its late messages still
    #: apply; replaced by the next run.
    run_id = Str()

    #: The tracked run is in progress.
    running = Bool(False)

    #: The backend has acknowledged the tracked run (a message of it came,
    #: or a preflight reply named it). Until then an idle preflight reply
    #: may predate the run request.
    run_acknowledged = Bool(False)

    #: An abort of the tracked run was requested.
    aborting = Bool(False)

    #: Run progress, percent over the whole run.
    progress = Int(0)

    #: The running test and step, or the pad / HV step being done.
    step_text = Str()

    #: The outcome line of the last run, refusal or request.
    summary = Str()

    #: The results, report and figures of the tracked run.
    outputs = Instance(SelfTestRunOutputs, ())

    #: The output view shown; a run switches it to the Report.
    output_view = Enum(OUTPUT_VIEW_REPORT, OUTPUT_VIEW_PLOTS)

    #: Backend-owned: the RAM-only calibration parts a save would keep.
    unsaved = List(Str)

    #: A save-calibration request is waiting on its reply.
    saving_calibration = Bool(False)

    #: The outcome of the last calibration save.
    calibration_status = Str()

    #: No run and no pre-flight in progress: the table and buttons are live.
    idle = Property(Bool, observe="running, pending_tests.items")

    #: The pre-flight check is showing.
    preflight_pending = Property(Bool, observe="pending_tests.items")

    can_save_report = Property(Bool, observe="outputs.report_markdown, running")

    can_save_calibration = Property(
        Bool, observe="unsaved.items, running, saving_calibration"
    )

    #: What the RAM holds unsaved, for the line beside the save button.
    unsaved_text = Property(Str, observe="unsaved.items")

    # ------------------------------------------------------------------ #
    # Defaults and properties                                              #
    # ------------------------------------------------------------------ #

    def _rows_default(self):
        # Imported here: the vendor module loads its service module on
        # import, which only an opened hub should pay for.
        from dropbot_portable import self_test

        return [
            SelfTestRow(
                name=name,
                title=self_test.test_title(name),
                pads=PADS_LABELS[self_test.TEST_PADS.get(name, self_test.PADS_ANY)],
            )
            for name in self_test.ALL_TESTS + self_test.HEALTH_TESTS
        ]

    def _get_idle(self):
        return not self.running and not self.pending_tests

    def _get_preflight_pending(self):
        return bool(self.pending_tests)

    def _get_can_save_report(self):
        return bool(self.outputs.report_markdown) and not self.running

    def _get_can_save_calibration(self):
        return bool(self.unsaved) and not self.running and not self.saving_calibration

    def _get_unsaved_text(self):
        if not self.unsaved:
            return ""

        parts = " and ".join(UNSAVED_PART_LABELS.get(p, p) for p in self.unsaved)

        return f"{parts[:1].upper()}{parts[1:]} in RAM only (until reboot)"

    # ------------------------------------------------------------------ #
    # Requests                                                             #
    # ------------------------------------------------------------------ #

    def selected_test_names(self):
        return [row.name for row in self.rows if row.selected]

    def all_test_names(self):
        return [row.name for row in self.rows]

    def request_preflight(self, tests, run_all=False):
        """Hold ``tests`` behind the pre-flight check; ``run_all`` marks a
        Run all."""

        if not tests:
            self.summary = "Self-test: select at least one test"

            return

        self.pending_tests = tests
        self.pending_run_all = run_all
        self.preflight.reset_for_run(
            [self._row(name).title for name in tests],
            tray_in_required(tests, run_all),
        )
        self.summary = "Pre-flight: check the board, then Start."

    def cancel_preflight(self):
        self.pending_tests = []
        self.summary = "Self-test not started (pre-flight cancelled)"

    def start_run(self):
        """Start tracking a run of the pending tests under a new run_id and
        return its SelfTestRunRequest fields; None when no tests are pending
        (a repeated Start must never replace the tracked run)."""
        tests = list(self.pending_tests)

        if not tests:
            return None

        request = {
            "run_id": uuid.uuid4().hex,
            "tests": tests,
            "test_kwargs": self.parameters.test_kwargs(tests),
            "chip_absent_acknowledged": self.preflight.chip_absent_acknowledged,
            "run_all": self.pending_run_all,
            "tray_in": self.preflight.wants_tray_in,
        }

        self.run_id = request["run_id"]
        self.running = True
        self.run_acknowledged = False
        self.aborting = False
        self.pending_tests = []

        self.outputs.clear()
        self.output_view = OUTPUT_VIEW_REPORT
        self.calibration_status = ""
        self.progress = 0
        self.step_text = ""
        self.summary = f"Self-test running ({len(tests)} test(s))..."

        for name in tests:
            self._row(name).show_outcome(OUTCOME_QUEUED)

        logger.info(f"Self-test run {self.run_id} requested: {', '.join(tests)}")

        return request

    def mark_aborting(self):
        """Note an abort request. A run the backend never acknowledged is
        dropped at once, since no finished message may ever come; returns
        True then, so the caller can ask the backend whether it runs after
        all (a preflight reply naming the run re-adopts it)."""

        if not self.run_acknowledged:
            self.running = False
            self.summary = "Self-test abandoned: the backend never acknowledged the run"
            self._mark_unfinished_rows()

            return True

        self.aborting = True
        self.summary = (
            "Stopping: the current step finishes, then HV off and the pads go back"
        )

        return False

    def save_calibration_request(self):
        """Request the save of the unsaved parts; return its fields."""
        self.saving_calibration = True
        self.calibration_status = "saving ..."

        return {
            "calibration": UNSAVED_CALIBRATION in self.unsaved,
            "tare": UNSAVED_TARE in self.unsaved,
        }

    # ------------------------------------------------------------------ #
    # Backend messages                                                     #
    # ------------------------------------------------------------------ #

    def apply_progress(self, progress):
        """Show a SelfTestProgress of the tracked run."""

        if not self.running or progress.run_id != self.run_id:
            return

        self.run_acknowledged = True

        if progress.phase == "choreography":
            self.step_text = progress.text

            return

        self.progress, self.step_text = _progress_percent_and_text(progress)

        if progress.phase == "start" and self._row(progress.name) is not None:
            self._row(progress.name).show_outcome(OUTCOME_RUNNING)

    def apply_result(self, result):
        """Keep a SelfTestResult of the tracked run: its row and outputs."""

        if not self.run_id or result.run_id != self.run_id:
            return

        self.run_acknowledged = True

        if self._row(result.name) is not None:
            self._row(result.name).show_result(result)

        self.outputs.add_result(result)

    def apply_finished(self, finished):
        """End the tracked run with its SelfTestFinished."""

        if not self.run_id or finished.run_id != self.run_id:
            return

        self.running = False
        self.aborting = False
        self.unsaved = list(finished.unsaved)
        self._mark_unfinished_rows()

        if finished.refused_reason:
            self.summary = f"Self-test not started: {finished.refused_reason}"
            self.step_text = ""

            return

        ran = [row for row in self.rows if row.name in self.outputs.results]
        outcomes = "; ".join(f"{row.title}: {row.outcome}" for row in ran)

        if finished.error:
            head = f"Self-test ABORTED ({finished.error})"

        elif finished.cancelled:
            head = "Self-test STOPPED"

        elif any(row.outcome_is_bad for row in ran):
            head = "Self-test FAILED"

        else:
            head = "Self-test done"
            self.progress = 100

        restore = finished.restore_note or "pads restored, HV off"
        self.summary = f"{head} -- {outcomes} ({restore})" if outcomes else head
        self.step_text = f"Finished: {restore}"
        logger.info(f"Self-test run {finished.run_id}: {self.summary}")

    def apply_preflight(self, reply):
        """Take a SelfTestPreflight: the checklist, the unsaved parts, and a
        resync of the run state for a panel reopened mid-run."""
        self.preflight.apply_reply(reply)
        self.unsaved = list(reply.unsaved)

        if reply.running and reply.run_id:
            if reply.run_id != self.run_id or not self.running:
                self._adopt_run(reply.run_id)

            self.run_acknowledged = True

            return

        if self.running and self.run_acknowledged:
            # The backend is idle, yet the finished message never came.
            self.running = False
            self.aborting = False
            self.summary = "Self-test ended without its final report (see the log)"
            self._mark_unfinished_rows()

    def apply_calibration_saved(self, saved):
        """Show a SelfTestCalibrationSaved and mirror a successful save into
        the results, so the regenerated report no longer says RAM only."""
        self.saving_calibration = False
        self.unsaved = list(saved.unsaved)

        if saved.error:
            self.calibration_status = f"Save FAILED: {saved.error}"

            return

        outcomes = []

        if saved.calibration_status == 0:
            outcomes.append("feedback-cap calibration saved")
            self.outputs.mark_saved(CALIBRATION_TEST, "cap_calibrate_saved")

        elif saved.calibration_status is not None:
            detail = saved.calibration_text or f"status {saved.calibration_status}"
            outcomes.append(f"feedback-cap calibration NOT saved ({detail})")

        if saved.tare_ok:
            outcomes.append("electrode tare saved")
            self.outputs.mark_saved(CHANNELS_TEST, "tare_capture", "saved")

        elif saved.tare_ok is not None:
            outcomes.append("electrode tare NOT saved (refused or no reply)")

        text = "; ".join(outcomes) or "nothing to save"
        self.calibration_status = f"{text[:1].upper()}{text[1:]}"

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _row(self, name):
        return next((row for row in self.rows if row.name == name), None)

    def _adopt_run(self, run_id):
        """Track a run this model did not start, or lost track of."""
        logger.info(f"Self-test hub resynced to the backend's run {run_id}")
        self.run_id = run_id
        self.running = True
        self.aborting = False
        self.summary = "Self-test running (resynced with the backend)"

    def _mark_unfinished_rows(self):
        for row in self.rows:
            if row.outcome in (OUTCOME_QUEUED, OUTCOME_RUNNING):
                row.show_outcome(OUTCOME_NOT_RUN)


def _progress_percent_and_text(progress):
    """(percent, "Test 2 of 7: boards (step 3 of 10)") of a test event, as
    the vendor's self-test tab words it."""
    total = max(1, progress.total)
    fraction = 0.0

    if progress.phase == "done":
        fraction = 1.0

    elif progress.phase == "step" and progress.steps:
        fraction = min(1.0, max(0.0, (progress.step or 0) / progress.steps))

    percent = round(100.0 * (progress.index + fraction) / total)
    text = f"Test {progress.index + 1} of {total}: {progress.name.replace('test_', '')}"

    if progress.phase == "step" and progress.steps:
        text += f" (step {(progress.step or 0) + 1} of {progress.steps})"

    elif progress.phase == "done":
        if progress.cancelled:
            text += " -- stopped"

        else:
            text += " -- ERROR" if progress.error else " -- done"

    return percent, text

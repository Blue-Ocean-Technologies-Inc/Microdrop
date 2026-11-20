# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test hub's backend: run, abort, pre-flight read and calibration
save, per the contract in ``portable_dropbot_self_tests.consts``.

A run executes on a daemon thread, like the PMT and fluorescence sessions:
the vendor tests block for minutes, past a Dramatiq actor's time limit. The
proxy lock is held per step (one HV off, one pad move with its read-back,
one single-test ``self_test`` call), never for the whole run; between steps
the status snapshot is republished, so the panes stay live and the status
watchdog keeps seeing answers.

While a run owns the board, ``_exclusive_owner_reason`` makes the
controller's listener refuse every request but SELF_TEST_ALLOWED_TOPICS; a
refused DISCONNECT becomes an abort, so the port never closes under a test
whose restore still has to switch the HV off. The motor E-STOP always
passes, and halts the run (``_on_motor_estop``). Pre-flight reads and the
unsaved-calibration state (``_self_test_unsaved``, which a run updates) are
``portable_dropbot_self_test_state_mixin_service``.

As the vendor runner (its worker's ``estop_queued`` signal), an E-STOP
ends the run: the test stops at its next step and the restore switches the
HV off without moving the pads. The vendor's 24 V rail-off halt
(``rails24_off``) has no controller signal and is not ported: it surfaces as
failing tests and pad moves, which end the run through the normal error
path. A lost link skips the restore moves.
"""

# Standard library imports.
import threading

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Any, HasTraits, Instance, Str, observe, provides

# Microdrop package imports.
from portable_dropbot_self_tests.consts import (
    SELF_TEST_ABORT,
    SELF_TEST_PREFLIGHT_READ,
    SELF_TEST_RUN,
    SelfTestAbortRequest,
    SelfTestRunRequest,
    self_test_finished_publisher,
)

# Local imports.
from ..consts import DISCONNECT, MOTOR_ESTOP
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from ..self_test_board import SelfTestBoard
from ..self_test_choreography import (
    execute_run,
    pads_state,
    read_board_state,
    start_refusal_reason,
    validate_run_request,
)
from ..self_test_results import (
    experiment_run_directory,
    run_id_echo,
    run_stamp,
    safe_verdicts,
    unsaved_parts,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The requests a running self-test lets through (see the contract).
SELF_TEST_ALLOWED_TOPICS = (SELF_TEST_ABORT, SELF_TEST_PREFLIGHT_READ, MOTOR_ESTOP)
#: Why a run's restore leaves the pads where they are after an E-STOP.
SELF_TEST_ESTOP_HALT = "E-STOP"
#: How long plugin stop waits for a cancelled run to restore (a pad move
#: alone may take 30 s).
SELF_TEST_JOIN_TIMEOUT_S = 45.0


@provides(IPortableDropbotControlMixinService)
class PortableDropbotSelfTestMixinService(HasTraits):
    id = Str("portable_dropbot_self_test_mixin_service")
    name = Str("Portable Dropbot Self Test Mixin")

    #: The run that owns the board; "" when idle. Set and cleared under
    #: `_self_test_claim`.
    _self_test_run_id = Str()
    #: Set by SELF_TEST_ABORT, a disconnect or cleanup; the choreography
    #: checks it between steps, the vendor tests at each of their steps.
    _self_test_cancel = Instance(threading.Event)
    #: The running run's daemon thread (see the module docstring).
    _self_test_thread = Instance(threading.Thread)
    #: Set by an E-STOP during the run: no pad move is sent after it, the
    #: restore's included (SelfTestBoard.move_pads). Reset by every claim.
    _self_test_halt_reason = Str()
    #: Serializes the run claim. `Instance(threading.Lock)` is rejected on
    #: the Pi's Python 3.12, hence `Any()` with a `_default`.
    _self_test_claim = Any()

    def __self_test_claim_default(self):
        return threading.Lock()

    # ------------------------------------------------------------------ #
    # Board ownership                                                     #
    # ------------------------------------------------------------------ #

    def _exclusive_owner_reason(self, topic):
        run_id = self._self_test_run_id

        if not run_id or topic in SELF_TEST_ALLOWED_TOPICS:
            return ""

        return f"self-test run {run_id} owns the Portable DropBot"

    def _on_request_refused(self, topic, message, reason):
        """Answer a refused run request with its one finished (the contract);
        a refused DISCONNECT during a run becomes the run's abort."""

        if topic == SELF_TEST_RUN:
            self._refuse_self_test(run_id_echo(message), reason)
        elif (
            topic == DISCONNECT
            and self.portable_dropbot_connection_active
            and self._self_test_cancel is not None
        ):
            self._self_test_cancel.set()
            logger.warning(
                f"Disconnect deferred: self-test run {self._self_test_run_id} "
                f"aborted instead; disconnect again once it has finished"
            )
        else:
            super()._on_request_refused(topic, message, reason)

    def _on_motor_estop(self):
        """Halt a running self-test, as the vendor runner does on an E-STOP:
        the test stops at its next step, the restore switches the HV off and
        no pad moves afterwards."""
        super()._on_motor_estop()

        with self._self_test_claim:
            cancel = self._self_test_cancel

            if cancel is not None:
                self._self_test_halt_reason = SELF_TEST_ESTOP_HALT

        if cancel is None:
            return

        cancel.set()
        logger.warning(
            f"Portable Dropbot E-STOP: self-test run {self._self_test_run_id} "
            f"halted; HV off, the pads are not moved"
        )

    def _board_session_reason(self):
        """Why another session or mode keeps the board from a self-test; the
        caller holds the PMT and fluorescence claims. A protocol run turns
        realtime mode on for its duration, so realtime covers protocols.
        Home All and a smart pad engage hold no proxy lock, so their own
        locks are checked."""

        if self.realtime_mode:
            return "realtime mode is on (a protocol may be running)"

        if self._home_all_lock.locked():
            return "Home All is running"

        if self._pad_engage_lock.locked():
            return "a smart chip lock or unlock is running"

        pmt_reason = self._pmt_busy_reason()

        if pmt_reason:
            return pmt_reason

        if self._fluorescence_capturing:
            return "a fluorescence capture is running"

        return ""

    def _claim_self_test(self, run_id):
        """Claim the board for ``run_id`` under the PMT, fluorescence and
        self-test claims at once, so no session can start in between.
        Returns ``(reason, cancel)``: reason "" when claimed."""

        with self._pmt_claim, self._fluorescence_claim, self._self_test_claim:
            if self._self_test_run_id:
                return "a self-test run is already in progress", None

            reason = self._board_session_reason()

            if reason:
                return reason, None

            cancel = threading.Event()
            self._self_test_cancel = cancel
            self._self_test_halt_reason = ""
            self._self_test_run_id = run_id

        return "", cancel

    @observe("portable_dropbot_connection_active")
    def _cancel_self_test_on_disconnect(self, event):
        """Every disconnect path clears this flag (see the fluorescence
        mixin). A new connection drops a run id whose thread is already
        gone."""

        if event.new:
            self._clear_stale_self_test_run()

            return

        cancel = self._self_test_cancel

        if cancel is not None:
            cancel.set()
            logger.warning("Portable Dropbot disconnected: self-test run cancelled")

    def _clear_stale_self_test_run(self):
        thread = self._self_test_thread

        with self._self_test_claim:
            if self._self_test_run_id and (thread is None or not thread.is_alive()):
                logger.warning(f"Stale self-test run {self._self_test_run_id} cleared")
                self._release_self_test_claim()

    def _release_self_test_claim(self):
        """Drop the run's ownership of the board; the caller holds
        `_self_test_claim`."""
        self._self_test_run_id = ""
        self._self_test_cancel = None

    def cleanup(self):
        """Cancel a running self-test and wait for its restore, then switch
        the HV off (best effort) before the connection teardown."""
        cancel = self._self_test_cancel
        thread = self._self_test_thread

        if cancel is not None:
            cancel.set()

        if thread is not None and thread.is_alive():
            thread.join(timeout=SELF_TEST_JOIN_TIMEOUT_S)

            # Bounded and past the proxy lock, which a run still stuck in a
            # driver call holds; never raises.
            self._deenergize("self-test teardown")

        super().cleanup()

    # ------------------------------------------------------------------ #
    # Requests                                                            #
    # ------------------------------------------------------------------ #

    def on_self_test_run_request(self, message):
        """Validate and claim, then hand the run to a daemon thread; the
        finished publish, from that thread, closes every run request. Any
        failure before the thread starts releases the claim and refuses."""
        run_id = run_id_echo(message)
        claimed = False

        try:
            request = SelfTestRunRequest.model_validate_json(str(message))
            tests, reason = validate_run_request(request.tests, request.test_kwargs)

            if not reason:
                reason, cancel = self._claim_self_test(request.run_id)

            if reason:
                self._refuse_self_test(request.run_id, reason)

                return

            claimed = True
            thread = threading.Thread(
                target=self._run_self_tests_and_finish,
                args=(request, tests, cancel),
                daemon=True,
                name="self-test",
            )
            thread.start()
            claimed = False
            self._self_test_thread = thread
            logger.info(f"Portable Dropbot self-test run {run_id}: {tests}")
        except Exception as error:
            # Broad except: validation errors and a failed thread start alike
            # must end in this run request's one finished message.
            logger.error(
                f"Self-test run {run_id!r} not started: {error}", exc_info=True
            )

            if claimed:
                with self._self_test_claim:
                    self._release_self_test_claim()

            self._refuse_self_test(run_id, str(error).splitlines()[0] or repr(error))

    def on_self_test_abort_request(self, message):
        try:
            request = SelfTestAbortRequest.model_validate_json(
                str(message).strip() or "{}"
            )
        except ValidationError as error:
            logger.warning(f"Self-test abort ignored: {error}")

            return

        with self._self_test_claim:
            run_id = self._self_test_run_id
            cancel = self._self_test_cancel

        if cancel is None or request.run_id not in ("", run_id):
            logger.info(f"Self-test abort ignored: run {request.run_id!r} not running")

            return

        cancel.set()
        logger.info(f"Portable Dropbot self-test run {run_id}: abort requested")

    # ------------------------------------------------------------------ #
    # The run (daemon thread)                                             #
    # ------------------------------------------------------------------ #

    def _run_self_tests_and_finish(self, request, tests, cancel):
        """Thread body: run, release the board, then publish the run's one
        finished message."""
        finished = {"run_id": request.run_id}

        try:
            finished.update(self._run_self_tests(request, tests, cancel))
        except Exception as error:
            # Broad except: whatever broke, the run must still release the
            # board and end with its finished message.
            logger.error(
                f"Portable Dropbot self-test run FAILED: {error}", exc_info=True
            )
            finished["error"] = str(error) or repr(error)
        finally:
            with self._self_test_claim:
                self._release_self_test_claim()

        finished["unsaved"] = list(self._self_test_unsaved)
        self._publish_finished(finished)
        logger.info(f"Portable Dropbot self-test run {request.run_id} --> {finished}")

    def _run_self_tests(self, request, tests, cancel):
        """Re-read the board, refuse or execute, then resync; returns the
        SelfTestFinished fields."""

        # The smart engage's pad positions are not the classic press the
        # choreography moves between, so guessing them is not safe.
        if self.pads_smart_engaged:
            return {"refused_reason": "release the smart chip lock before self-tests"}

        bot = self.proxy
        ok, reads = self._proxy_call(
            "self-test start read", lambda: read_board_state(bot)
        )

        if not ok:
            return {"refused_reason": f"board state not read: {reads or 'no reply'}"}

        # A session that slipped past the listener's gate before the claim
        # (its request was already dispatched) has claimed by now. Residual
        # risk: the PMT and fluorescence claims do not check for a self-test
        # (those files are at their length baselines), so a request
        # dispatched before the claim that claims only after this re-check
        # would still run alongside; the window is its handler's validation.
        with self._pmt_claim, self._fluorescence_claim:
            reason = self._board_session_reason()

        reason = reason or start_refusal_reason(
            tests, reads, request.chip_absent_acknowledged
        )

        if reason:
            return {"refused_reason": reason}

        stamp = run_stamp()
        board = SelfTestBoard(
            controller=self,
            bot=bot,
            run_id=request.run_id,
            tests=tests,
            test_kwargs=request.test_kwargs,
            cancel=cancel,
            directory=experiment_run_directory(stamp),
            stamp=stamp,
        )

        summary = {}

        try:
            summary = execute_run(tests, pads_state(reads["pads"]), board, cancel)
        finally:
            self._resync_after_self_test(board, summary.get("hv_off_confirmed", False))

        error = summary["error"]

        if self._self_test_halt_reason:
            error = error or f"{self._self_test_halt_reason}: the run was halted"

        if board.link_lost():
            error = error or "the Portable DropBot disconnected during the run"
        else:
            self._self_test_unsaved = unsaved_parts(
                summary["results"], self._self_test_unsaved
            )

        return {
            "cancelled": cancel.is_set(),
            "error": error,
            "restore_note": summary["restore_note"],
            "verdicts": safe_verdicts(summary["results"]),
            "directory": "" if board.directory is None else str(board.directory),
        }

    def _resync_after_self_test(self, board, hv_off_confirmed):
        """Put the controller's picture back on the board and republish it.

        The vendor tests' restore puts back their own snapshot: the HV
        setpoint (or the 35 V resting value), the frequency and the
        snapshot's electrodes. A run only starts with realtime mode off, so
        the controller's picture is no electrodes, HV off and its own cached
        voltage and frequency. The setpoint is only pushed behind a confirmed
        HV off, and followed by another off, as a fresh connect does.
        """

        if board.link_lost():
            return

        with self._proxy_lock:
            if hv_off_confirmed:
                self._apply_actuation()

            self._proxy_call(
                "self-test: clear channels", lambda: self.proxy.clear_channels()
            )
            self._proxy_call(
                "self-test: HV off", lambda: self.proxy.sig.hv_enable(0, 0)
            )

        self._publish_realtime_mode()
        self._publish_status_snapshot()

    # ------------------------------------------------------------------ #
    # Replies                                                             #
    # ------------------------------------------------------------------ #

    def _refuse_self_test(self, run_id, reason):
        logger.warning(f"Portable Dropbot self-test run {run_id!r} refused: {reason}")
        self._publish_finished(
            {
                "run_id": run_id,
                "refused_reason": reason,
                "unsaved": list(self._self_test_unsaved),
            }
        )

    def _publish_finished(self, finished):
        # Logged, never raised: the finished message is the last thing a run
        # does, after the board is already released.
        try:
            self_test_finished_publisher.publish(finished)
        except Exception as error:
            logger.error(f"Self-test finished not published: {error}")

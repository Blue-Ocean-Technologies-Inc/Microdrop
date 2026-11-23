# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test hub's state between runs: pre-flight reads and the
backend-owned unsaved-calibration state with its flash save, per the
contract in ``portable_dropbot_self_tests.consts``. The run itself is
``portable_dropbot_self_test_mixin_service``; this mixin reads its
``_self_test_run_id`` and the run writes ``_self_test_unsaved`` here.
"""

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from traits.api import HasTraits, List, Str, observe, provides

# Microdrop package imports.
from portable_dropbot_self_tests.consts import (
    PREFLIGHT_BOARD_BUSY_ERROR,
    SELF_TEST_PREFLIGHT_READ,
    SELF_TEST_SAVE_CALIBRATION,
    UNSAVED_CALIBRATION,
    UNSAVED_TARE,
    SelfTestSaveCalibrationRequest,
    self_test_calibration_saved_publisher,
    self_test_preflight_publisher,
)

# Local imports.
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from ..self_test_choreography import preflight_fields, read_board_state
from ..self_test_results import cap_calibration_save_outcome, elec_tare_save_outcome

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotSelfTestStateMixinService(HasTraits):
    id = Str("portable_dropbot_self_test_state_mixin_service")
    name = Str("Portable Dropbot Self Test State Mixin")

    #: UNSAVED_PARTS the board holds in RAM only (backend-owned, see the
    #: contract's "Unsaved calibration").
    _self_test_unsaved = List(Str)

    @observe("portable_dropbot_connection_active")
    def _forget_unsaved_on_disconnect(self, event):
        """The board's RAM calibration goes with the connection."""

        if not event.new:
            self._self_test_unsaved = []

    def _on_request_refused(self, topic, message, reason):
        """Answer a refused pre-flight read or save with its reply's error,
        as the contract promises."""

        if topic == SELF_TEST_PREFLIGHT_READ:
            self._publish_preflight({"error": reason})
        elif topic == SELF_TEST_SAVE_CALIBRATION:
            self._publish_calibration_saved({"error": reason})
        else:
            super()._on_request_refused(topic, message, reason)

    def on_self_test_preflight_read_request(self, message):
        """Board state for the pre-run checklist plus the hub's own state.
        While a run owns the link the board is not read: the reply carries
        the run state only (board fields None)."""
        self._publish_preflight(
            {} if self._self_test_run_id else self._read_preflight()
        )

    def on_self_test_save_calibration_request(self, message):
        try:
            request = SelfTestSaveCalibrationRequest.model_validate_json(
                str(message).strip() or "{}"
            )
        except ValidationError as error:
            self._publish_calibration_saved({"error": str(error).splitlines()[0]})

            return

        reply = {}
        errors = []

        if request.calibration:
            errors.append(
                self._save_calibration_part(
                    reply,
                    UNSAVED_CALIBRATION,
                    lambda: self.proxy.uart.saveCapCalibration(),
                    cap_calibration_save_outcome,
                )
            )

        if request.tare:
            errors.append(
                self._save_calibration_part(
                    reply,
                    UNSAVED_TARE,
                    lambda: self.proxy.uart.saveElecTare(),
                    elec_tare_save_outcome,
                )
            )

        if not (request.calibration or request.tare):
            errors.append("nothing selected to save")

        reply["error"] = "; ".join(error for error in errors if error)
        self._publish_calibration_saved(reply)

    def _read_preflight(self):
        """The pre-flight board fields, or the error that kept them unread.
        A held lock is a long locked sequence (a self-test step, the
        calibration macro): waiting on it would stall this worker, so the
        reply says busy instead."""

        if not self._proxy_lock.acquire(blocking=False):
            return {"error": PREFLIGHT_BOARD_BUSY_ERROR}

        try:
            ok, reads = self._proxy_call(
                "self-test preflight read", lambda: read_board_state(self.proxy)
            )
        finally:
            self._proxy_lock.release()

        if not ok:
            return {"error": f"board state not read: {reads or 'no reply'}"}

        return preflight_fields(reads)

    def _save_calibration_part(self, reply, part, save, decode):
        """Run one flash save, decode its outcome into ``reply`` and clear
        ``part`` from the unsaved state when it saved; returns the failure,
        "" on success."""
        fields, error = decode(*self._proxy_call(f"self-test: save {part}", save))
        reply.update(fields)

        if not error:
            self._discard_unsaved(part)

        return error

    def _discard_unsaved(self, part):
        self._self_test_unsaved = [
            unsaved for unsaved in self._self_test_unsaved if unsaved != part
        ]

    def _publish_preflight(self, preflight):
        """Publish ``preflight`` plus the hub's own state (running, run_id,
        unsaved), so a reopened panel can resync."""
        preflight.update(
            running=bool(self._self_test_run_id),
            run_id=self._self_test_run_id,
            unsaved=list(self._self_test_unsaved),
        )

        try:
            self_test_preflight_publisher.publish(preflight)
        except Exception as error:
            logger.error(f"Self-test preflight not published: {error}")

    def _publish_calibration_saved(self, reply):
        reply["unsaved"] = list(self._self_test_unsaved)
        logger.info(f"Portable Dropbot self-test calibration save --> {reply}")

        try:
            self_test_calibration_saved_publisher.publish(reply)
        except Exception as error:
            logger.error(f"Self-test calibration save reply not published: {error}")

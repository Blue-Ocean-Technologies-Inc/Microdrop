# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater verify run (dropbot-portable 1.8.0 ``heater_tune.VerifyRun``):
regulate one heater to a set point on the gains the board holds, typically
right after an apply, and report the response (``heater_tune_verify``).

It is a run of the heater-tune mixin in every respect but the state
machine: the same start rules (both heaters off, no protocol step holding a
target, the cap below the board's ceiling) checked under the same claim,
the same daemon thread, and so the same heater ownership while it runs and
the same ends with the heater switched off (HEATER_TUNE_CANCEL, an E-STOP,
a heater failsafe alarm, a disconnect, plugin stop, a lost link). Composed
after the heater-tune mixin, before the temp and self-test mixins: its
``_on_request_refused`` must run before theirs."""

# Third-party imports.
from dropbot_portable.heater_tune import verify_problem
from pydantic import ValidationError

# Enthought library imports.
from traits.api import HasTraits, Str, provides

# Local imports.
from ..consts import (
    HEATER_TUNE_VERIFY_PHASE,
    HEATER_TUNE_VERIFY_START,
    HeaterTuneVerifyStartRequest,
    heater_tune_progress_publisher,
    heater_tune_verify_done_publisher,
)
from ..heater_tune_board import heater_request_channel
from ..heater_tune_verify import run_verify, summarize_verify, verify_config
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotHeaterTuneVerifyMixinService(HasTraits):
    id = Str("portable_dropbot_heater_tune_verify_mixin_service")
    name = Str("Portable Dropbot Heater Tune Verify Mixin")

    def _on_request_refused(self, topic, message, reason):
        """Answer a refused verify request on its done topic (the contract
        replies to every start)."""

        if topic == HEATER_TUNE_VERIFY_START:
            self._refuse_heater_tune_verify(heater_request_channel(message), reason)

        super()._on_request_refused(topic, message, reason)

    def on_heater_tune_verify_start_request(self, message):
        """Check the start rules under the tune claim, then hand the run to a
        daemon thread; its HEATER_TUNE_VERIFY_DONE closes every request."""

        try:
            request = HeaterTuneVerifyStartRequest.model_validate_json(str(message))
        except ValidationError as error:
            self._refuse_heater_tune_verify(
                heater_request_channel(message), error.errors()[0]["msg"]
            )

            return

        started = self._start_heater_tune_run(
            request,
            lambda current_c: verify_problem(verify_config(request), current_c),
            self._run_heater_tune_verify,
            self._refuse_heater_tune_verify,
            "heater-tune-verify",
        )

        if not started:
            return

        logger.info(
            f"Portable Dropbot heater verify ch{request.channel}: set point "
            f"{request.setpoint_c:g} °C ±{request.band_c:g} °C for "
            f"{request.hold_s} s, cap {request.max_temp_c:g} °C, limit "
            f"{request.max_duration_s} s"
        )

    def _run_heater_tune_verify(self, request, cancel):
        """The regulated run, its metrics and the done publish."""

        def verify(board):
            run, off_confirmed = run_verify(
                board,
                verify_config(request),
                cancel,
                self._publish_heater_tune_verify_progress,
            )

            return summarize_verify(run), off_confirmed

        self._finish_heater_tune_run(
            "verify", request.channel, verify, heater_tune_verify_done_publisher
        )

    def _publish_heater_tune_verify_progress(self, run, current_c):
        """One reading of the run, with the loop output the board reported
        as its duty."""
        samples = run.samples
        elapsed_s = samples[-1][0] - run.t0 if samples else 0.0
        output_pct = samples[-1][2] if samples else None

        heater_tune_progress_publisher.publish(
            {
                "channel": run.cfg.channel,
                "phase": HEATER_TUNE_VERIFY_PHASE,
                "elapsed_s": round(elapsed_s, 1),
                "current_c": current_c,
                "duty_pct": round(output_pct or 0),
                "setpoint_c": run.cfg.setpoint_c,
            }
        )

    def _refuse_heater_tune_verify(self, channel, reason):
        logger.warning(f"Portable Dropbot heater verify ch{channel} refused: {reason}")
        heater_tune_verify_done_publisher.publish(
            {"channel": channel, "ok": False, "reason": reason}
        )

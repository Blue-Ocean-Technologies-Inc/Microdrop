# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Capacitance-calibration requests: the vendor's hardware-validated
ML calibration macro plus the ML-path/gain/cal-caps provisioning
around it, driven from the calibration pane."""

# Standard library imports.
import json

# Third-party imports.
from dropbot_portable import MotorBoard
from dropbot_portable.portable_dropbot_service import CmdStatus
from dropbot_portable.proxy import SignalBoardCmd

# Enthought library imports.
from traits.api import HasTraits, Str, provides

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    CAL_CAPS_CHOICES,
    CAL_FREQUENCY,
    CAL_VOLTAGE,
    CALIBRATION_UPDATED,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from ..motion_replies import mechanism_failure

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: How a step the board refused as BUSY reads: not run, worth a retry.
CALIBRATION_BUSY_TEXT = "BUSY, retry"


@provides(IPortableDropbotControlMixinService)
class PortableDropbotCalibrationMixinService(HasTraits):
    id = Str("portable_dropbot_calibration_mixin_service")
    name = Str("Portable Dropbot Calibration Mixin")

    def _publish_calibration(self, **payload):
        publish_message(topic=CALIBRATION_UPDATED, message=json.dumps(payload))

    def on_run_cap_calibration_request(self, message):
        """The validated multi-slope calibration macro, verbatim from
        the vendor UI: clear -> release pogos -> 100 V/10 kHz -> HV
        enable BYPASS -> re-clear -> multi-slope fit (~6 s) -> HV
        disable -> restore V/F -> press pogos. Each reply is judged as the
        vendor does (HV_ENABLE and CAP_CALIBRATE_ML status bytes, BUSY
        reported as a retry). A failed setup step skips straight to the
        teardown (HV off, restore V/F, press pogos), which always runs, so
        HV is never left energized and the pogos come back down; each
        step's outcome streams to the pane."""
        if self.proxy is None:
            logger.warning(
                "Portable Dropbot not connected: ignoring "
                "capacitance calibration request."
            )
            return

        logger.info("Portable Dropbot ML capacitance calibration macro started")
        uart, sig = self.proxy.uart, self.proxy.sig

        def clear_electrodes():
            return uart.setElectrodeStates([False] * uart.board_channels)

        setup = (
            ("clear electrodes", clear_electrodes, self._calibration_reply_failure),
            ("release pogos", lambda: uart.setPogo(0), self._calibration_pogo_failure),
            (
                f"set {CAL_VOLTAGE} V / {CAL_FREQUENCY} Hz",
                lambda: self.proxy.set_actuation(CAL_VOLTAGE, CAL_FREQUENCY),
                self._calibration_reply_failure,
            ),
            (
                "enable HV (bypass)",
                lambda: sig.hv_enable(1, 1),
                lambda reply: self._calibration_hv_failure(True, reply),
            ),
            ("re-clear electrodes", clear_electrodes, self._calibration_reply_failure),
            (
                "multi-slope calibration",
                lambda: sig.cap_calibrate_ml(0),
                self._cap_calibrate_failure,
            ),
        )
        teardown = (
            (
                "disable HV",
                lambda: sig.hv_enable(0, 0),
                lambda reply: self._calibration_hv_failure(False, reply),
            ),
            (
                "restore V/F",
                lambda: (self._apply_actuation(), True)[1],
                self._calibration_reply_failure,
            ),
            ("press pogos", lambda: uart.setPogo(1), self._calibration_pogo_failure),
        )
        failures = []

        # One lock for the whole macro (RLock, so the nested
        # _proxy_call re-enters): the 2 s status poll must not
        # interleave its own commands into the calibration sequence.
        with self._proxy_lock:
            for step in setup:
                failure = self._run_calibration_step(*step)

                if failure:
                    failures.append(failure)
                    break

            for step in teardown:
                failure = self._run_calibration_step(*step)

                if failure:
                    failures.append(failure)

        retry = any(CALIBRATION_BUSY_TEXT in failure for failure in failures)

        self._publish_calibration(
            stage="done", ok=not failures, error="; ".join(failures), retry=retry
        )
        logger.info(
            f"Portable Dropbot ML capacitance calibration macro --> "
            f"{'; '.join(failures) or 'ok'}"
        )

    def _run_calibration_step(self, stage, call, judge):
        """Run one macro step and stream its outcome; returns "stage (why)"
        when it failed, else ""."""
        ok, result = self._proxy_call(f"calibration: {stage}", call)
        error = judge(result) if ok else f"driver error: {result}"

        self._publish_calibration(stage=stage, ok=not error, error=error)
        logger.info(f"Calibration step {stage!r}: {error or 'ok'}")

        return f"{stage} ({error})" if error else ""

    def _last_reply_text(self, cmd=None):
        """The driver's account of this thread's last request (FAIL, BUSY or
        TIMEOUT), or "no reply"."""
        result = self.proxy.uart.last_result(cmd)

        return result.describe() if result is not None else "no reply"

    def _calibration_reply_failure(self, reply):
        if reply is None or reply is False:
            return self._last_reply_text()

        return ""

    def _calibration_pogo_failure(self, reply):
        return mechanism_failure(reply, self.proxy.uart, MotorBoard.PUSHPAD_CTRL) or ""

    def _calibration_hv_failure(self, enable, reply):
        """HV_ENABLE must answer "HV on" to the bypass enable and "HV off" to
        the disable; 2-5 are refusals (3 = busy, retry)."""
        if reply is None:
            return self._last_reply_text(SignalBoardCmd.HV_ENABLE)

        accepted, outcome = self._hv_enable_outcome(enable, reply.status)

        return "" if accepted else outcome

    def _cap_calibrate_failure(self, reply):
        """CAP_CALIBRATE_ML answers status 1 when the fit is done; a BUSY
        refusal means it did not run (the electrode chain could not be
        owned) and is worth a retry."""
        if reply is not None:
            return "" if reply.status == 1 else f"status {reply.status} (not done)"

        result = self.proxy.uart.last_result(SignalBoardCmd.CAP_CALIBRATE_ML)

        if result is not None and result.status == CmdStatus.BUSY:
            return f"{CALIBRATION_BUSY_TEXT}: the electrode chain was in use, not run"

        return result.describe() if result is not None else "no reply"

    def on_set_ml_realtime_request(self, message):
        on = str(message) == "True"
        ok, mode = self._proxy_call(
            "ML realtime path", lambda: self.proxy.sig.cap_ml_realtime(1 if on else 0)
        )
        if ok and mode is not None:
            self._publish_calibration(ml_realtime=mode.current == 1)
        logger.info(
            f"Portable Dropbot ML realtime path --> {on}: "
            f"{'ok' if ok and mode is not None else 'FAILED'}"
        )

    def on_read_electrode_gain_request(self, message):
        ok, gain = self._proxy_call(
            "read electrode gain", lambda: self.proxy.sig.cap_elec_gain(0)
        )
        if ok and gain is not None:
            self._publish_calibration(electrode_gain=int(gain.current))
        else:
            logger.warning("Portable Dropbot electrode gain read FAILED")

    def on_set_electrode_gain_request(self, message):
        permille = int(float(str(message)))
        ok, gain = self._proxy_call(
            f"set electrode gain {permille}",
            lambda: self.proxy.sig.cap_elec_gain(permille),
        )
        if ok and gain is not None:
            self._publish_calibration(electrode_gain=int(gain.current))
        logger.info(
            f"Portable Dropbot electrode gain --> {permille} "
            f"permille: "
            f"{'ok' if ok and gain is not None else 'FAILED'}"
        )

    def on_read_cal_caps_request(self, message):
        ok, n = self._proxy_call("read cal caps", lambda: self.proxy.sig.cal_caps_get())
        if ok and n is not None:
            self._publish_calibration(cal_caps=int(n.cal_caps))
        else:
            logger.warning("Portable Dropbot cal-caps read FAILED")

    def on_set_cal_caps_request(self, message):
        n = int(str(message))
        if n not in CAL_CAPS_CHOICES:
            logger.warning(f"Invalid cal-caps count: {n}")
            return
        ok, echoed = self._proxy_call(
            f"set cal caps {n}", lambda: self.proxy.sig.cal_caps_set(n)
        )
        if ok and echoed is not None:
            self._publish_calibration(cal_caps=int(echoed.cal_caps))
        logger.info(
            f"Portable Dropbot cal caps --> {n}: "
            f"{'ok' if ok and echoed is not None else 'FAILED'}"
        )

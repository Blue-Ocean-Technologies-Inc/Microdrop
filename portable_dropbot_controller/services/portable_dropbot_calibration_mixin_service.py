"""Capacitance-calibration requests: the vendor's hardware-validated
ML calibration macro plus the ML-path/gain/cal-caps provisioning
around it, driven from the calibration pane."""
import json

from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import (
    CAL_CAPS_CHOICES, CAL_FREQUENCY, CAL_VOLTAGE, CALIBRATION_UPDATED,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotCalibrationMixinService(HasTraits):
    id = Str("portable_dropbot_calibration_mixin_service")
    name = Str("Portable Dropbot Calibration Mixin")

    def _publish_calibration(self, **payload):
        publish_message(topic=CALIBRATION_UPDATED,
                        message=json.dumps(payload))

    def on_run_cap_calibration_request(self, message):
        """The validated multi-slope calibration macro, verbatim from
        the vendor UI: clear -> release pogos -> 100 V/10 kHz -> HV
        enable BYPASS -> re-clear -> multi-slope fit (~6 s) -> HV
        disable -> restore V/F -> press pogos. Every step runs (even
        after an earlier failure) so HV is never left energized and
        the pogos always come back down; each step's outcome streams
        to the pane."""
        if self.proxy is None:
            return
        uart = self.proxy.uart

        def clear_electrodes():
            return uart.setElectrodeStates([False] * uart.board_channels)

        steps = (
            ("clear electrodes", clear_electrodes),
            ("release pogos", lambda: uart.setPogo(0)),
            (f"set {CAL_VOLTAGE} V / {CAL_FREQUENCY} Hz",
             lambda: self.proxy.set_actuation(CAL_VOLTAGE,
                                              CAL_FREQUENCY)),
            ("enable HV (bypass)", lambda: uart.hv_enable(1, 1)),
            ("re-clear electrodes", clear_electrodes),
            ("multi-slope calibration",
             lambda: uart.cap_calibrate_ml(0)),
            ("disable HV", lambda: uart.hv_enable(0, 0)),
            ("restore V/F", lambda: (self._apply_actuation(), True)[1]),
            ("press pogos", lambda: uart.setPogo(1)),
        )
        # One lock for the whole macro (RLock, so the nested
        # _proxy_call re-enters): the 2 s status poll must not
        # interleave its own commands into the calibration sequence.
        all_ok = True
        with self._proxy_lock:
            for stage, call in steps:
                ok, result = self._proxy_call(f"calibration: {stage}",
                                              call)
                ok = ok and result is not None and result is not False
                all_ok = all_ok and ok
                self._publish_calibration(stage=stage, ok=ok)
                logger.info(f"Calibration step {stage!r}: "
                            f"{'ok' if ok else 'FAILED'}")
        self._publish_calibration(stage="done", ok=all_ok)

    def on_set_ml_realtime_request(self, message):
        on = str(message) == "True"
        ok, mode = self._proxy_call(
            "ML realtime path",
            lambda: self.proxy.uart.cap_ml_realtime(1 if on else 0))
        if ok and mode is not None:
            self._publish_calibration(ml_realtime=mode == 1)
        logger.info(f"Portable Dropbot ML realtime path --> {on}")

    def on_read_electrode_gain_request(self, message):
        ok, gain = self._proxy_call(
            "read electrode gain",
            lambda: self.proxy.uart.cap_elec_gain(0))
        if ok and gain is not None:
            self._publish_calibration(electrode_gain=int(gain))

    def on_set_electrode_gain_request(self, message):
        permille = int(float(str(message)))
        ok, gain = self._proxy_call(
            f"set electrode gain {permille}",
            lambda: self.proxy.uart.cap_elec_gain(permille))
        if ok and gain is not None:
            self._publish_calibration(electrode_gain=int(gain))
        logger.info(f"Portable Dropbot electrode gain --> {permille} "
                    f"permille")

    def on_read_cal_caps_request(self, message):
        ok, n = self._proxy_call("read cal caps",
                                 lambda: self.proxy.uart.cal_caps_get())
        if ok and n is not None:
            self._publish_calibration(cal_caps=int(n))

    def on_set_cal_caps_request(self, message):
        n = int(str(message))
        if n not in CAL_CAPS_CHOICES:
            logger.warning(f"Invalid cal-caps count: {n}")
            return
        ok, echoed = self._proxy_call(
            f"set cal caps {n}",
            lambda: self.proxy.uart.cal_caps_set(n))
        if ok and echoed is not None:
            self._publish_calibration(cal_caps=int(echoed))
        logger.info(f"Portable Dropbot cal caps --> {n}")

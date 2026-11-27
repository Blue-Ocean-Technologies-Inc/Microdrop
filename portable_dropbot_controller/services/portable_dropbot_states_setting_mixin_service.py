# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Third-party imports.
from dropbot_portable.self_test import HV_ENABLE_STATUS_TEXT
from pydantic import ValidationError

# Enthought library imports.
from traits.api import HasTraits, Str, provides

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..actuation_limits import frequency_refusal, voltage_refusal
from ..board_alarms import clear_board_alarms, summarize_alarms_cleared
from ..consts import (
    FLUORESCENCE_LED_RAW_MAX,
    FREQUENCY_APPLIED,
    HV_ENABLE_STATUS_OFF,
    HV_ENABLE_STATUS_ON,
    LIGHT_INTENSITY_RAW_MAX,
    RGB_LIGHT_STATES,
    VOLTAGE_APPLIED,
    AlarmsCleared,
    ClearAlarmsRequest,
    alarms_cleared_publisher,
)
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotStatesSettingMixinService(HasTraits):
    id = Str("portable_dropbot_states_setting_mixin_service")
    name = Str("Portable Dropbot States Setting Mixin")

    def on_set_realtime_mode_request(self, message):
        """The vendor UI's HV On/Off follows realtime mode here: HV only
        energizes while realtime is on (pad-interlocked, no bypass — the
        firmware still refuses without a device on the pads), and leaving
        realtime kills it."""

        if str(message) != "True":
            self._leave_realtime_mode()
            return

        ok, reply = self._proxy_call(
            "HV enable", lambda: self.proxy.sig.hv_enable(1, 0)
        )
        accepted, outcome = self._hv_enable_outcome(
            True, getattr(reply, "status", None)
        )

        # Realtime turns on only once HV is: a refused or failed enable
        # leaves both off, so the pane never shows realtime over a dead HV.
        if ok and accepted:
            self.realtime_mode = True
            self._publish_realtime_mode()
            logger.info(f"Portable Dropbot realtime mode on; HV enable --> {outcome}")
            return

        # A raised failure has already been reported by _proxy_call.
        if ok:
            self._publish_error("HV enable", outcome)

    def _leave_realtime_mode(self):
        """Leave realtime mode: de-energize HV, then release every electrode
        (the vendor's halt order). Both skip the proxy lock, like a motor
        stop: switching HV off must never queue behind a long call holding
        it, and each is a single request the driver matches to its reply."""
        self.realtime_mode = False
        self._publish_realtime_mode()

        ok, reply = self._proxy_call(
            "HV disable", lambda: self.proxy.sig.hv_enable(0, 0), serialize=False
        )
        self._proxy_call(
            "clear channels", lambda: self.proxy.clear_channels(), serialize=False
        )

        # A raised failure has already been reported by _proxy_call.
        if not ok:
            return

        accepted, outcome = self._hv_enable_outcome(
            False, getattr(reply, "status", None)
        )

        if accepted:
            logger.info(f"Portable Dropbot realtime mode off; HV disable --> {outcome}")
        else:
            self._publish_error("HV disable", outcome)

    @staticmethod
    def _hv_enable_outcome(enable, status):
        """Judge an HV_ENABLE reply status byte the way the vendor does:
        (accepted, text). Only "HV on" answers an enable and only "HV off"
        a disable; 2-5 are refusals (no device on the pads, busy, 24 V
        domain off, halt latched) and None is no reply."""

        if status is None:
            return False, "no reply"

        expected = HV_ENABLE_STATUS_ON if enable else HV_ENABLE_STATUS_OFF
        text = HV_ENABLE_STATUS_TEXT.get(int(status), f"unknown status {status}")

        return int(status) == expected, text

    def on_clear_halt_request(self, message):
        """Clear a latched firmware halt (HALT_CLEAR). It never re-enables
        anything: HV stays off until realtime mode enables it again. A
        refusal (the cause persists) is reported with its blocking types."""
        ok, result = self._proxy_call("halt clear", lambda: self.proxy.clear_halt())

        if not ok:
            return

        if result is None:
            self._publish_error("halt clear", "no reply (firmware without the latch?)")
        elif result.refused:
            self._publish_error("halt clear", result.describe())
        else:
            logger.info(f"Portable Dropbot halt clear --> {result.describe()}")

        self._publish_status_snapshot()

    def on_clear_alarms_request(self, message):
        """Clear latched board alarms (CLEAR_ALARM), each board under the
        proxy lock: its active alarms (or the requested codes) are cleared,
        then re-read. An alarm whose condition persists is reported as
        still active on ALARMS_CLEARED, never raised."""

        try:
            request = ClearAlarmsRequest.model_validate_json(str(message) or "{}")
        except ValidationError as error:
            self._publish_error("alarm clear", error.errors()[0]["msg"])

            return

        results = []

        for board in request.boards:
            ok, result = self._proxy_call(
                f"{board} alarm clear",
                lambda: clear_board_alarms(self.proxy, board, request.codes),
            )

            if not ok:
                result = {"board": board, "error": str(result or "not connected")}

            results.append(result)

        outcome = AlarmsCleared(results=results)

        alarms_cleared_publisher.publish(outcome.model_dump())
        logger.info(
            f"Portable Dropbot alarm clear --> "
            f"{summarize_alarms_cleared(outcome.results)}"
        )

    def on_set_voltage_request(self, message):
        self._set_voltage(int(float(str(message))))

    def on_set_frequency_request(self, message):
        self._set_frequency(int(float(str(message))))

    def on_protocol_set_voltage_request(self, message):
        """A protocol step's voltage, on the DropBot's shared topic: acked
        on VOLTAGE_APPLIED (the volts, as the DropBot does) only once the
        board took it, so a refused setpoint fails the step on its ack
        wait."""
        voltage = int(float(str(message)))

        if self._set_voltage(voltage):
            publish_message(topic=VOLTAGE_APPLIED, message=str(voltage))

    def on_protocol_set_frequency_request(self, message):
        """A protocol step's frequency, acked on FREQUENCY_APPLIED like the
        voltage (see on_protocol_set_voltage_request)."""
        frequency = int(float(str(message)))

        if self._set_frequency(frequency):
            publish_message(topic=FREQUENCY_APPLIED, message=str(frequency))

    def _set_voltage(self, voltage):
        """Apply a voltage setpoint and return whether the board took it.
        One the HV supply would refuse is reported and the current setpoint
        kept."""
        refusal = voltage_refusal(voltage)

        if refusal:
            self._publish_error("set voltage", f"{refusal}; kept {self.voltage} V")

            return False

        self.voltage = voltage
        applied = self._apply_actuation()

        if applied:
            logger.info(f"Portable Dropbot voltage set to {self.voltage} V")

        return applied

    def _set_frequency(self, frequency):
        """Apply a frequency setpoint and return whether the board took it.
        One the HV supply would refuse is reported and the current setpoint
        kept."""
        refusal = frequency_refusal(frequency)

        if refusal:
            self._publish_error("set frequency", f"{refusal}; kept {self.frequency} Hz")

            return False

        self.frequency = frequency
        applied = self._apply_actuation()

        if applied:
            logger.info(f"Portable Dropbot frequency set to {self.frequency} Hz")

        return applied

    def on_set_light_intensity_request(self, message):
        self.light_intensity = int(float(str(message)))
        self._apply_light_intensity()

        if self.preferences is not None:
            # Persisted as the next connect's default, as before.
            self.preferences.default_light_intensity = self.light_intensity

        logger.info(f"Portable Dropbot light intensity set to {self.light_intensity} %")

    def on_set_light_on_request(self, message):
        self.light_on = str(message) == "True"
        self._apply_light_intensity()
        logger.info(f"Portable Dropbot illumination {'on' if self.light_on else 'off'}")

    def on_set_rgb_light_request(self, message):
        color = str(message).strip().lower()
        if color not in RGB_LIGHT_STATES:
            logger.warning(f"Unknown RGB light state: {color!r}")
            return

        ok, result = self._proxy_call(
            f"rgb light {color}", lambda: self.proxy.uart.setBoxLight(color)
        )
        logger.info(
            f"Portable Dropbot RGB light --> {color}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    def on_set_illumination_raw_request(self, message):
        """Vendor-style raw illumination brightness, 0-255 straight
        to the firmware — no % scaling."""
        raw = min(max(0, int(float(str(message)))), LIGHT_INTENSITY_RAW_MAX)
        # The generated proxy packs the firmware's own width (1 byte here,
        # 2 bytes for the fluorescence LED); the uart facade's
        # setLEDIntensity clamps to 0-100 and halves whatever it is given.
        ok, result = self._proxy_call(
            f"illumination raw {raw}",
            lambda: self.proxy.sig.illumination_ctrl(raw),
        )
        logger.info(
            f"Portable Dropbot illumination raw --> {raw}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

    def on_set_fluorescence_led_raw_request(self, message):
        """Vendor-style raw fluorescence LED brightness, 16-bit
        0-65535 straight to the firmware."""
        raw = min(max(0, int(float(str(message)))), FLUORESCENCE_LED_RAW_MAX)
        ok, result = self._proxy_call(
            f"fluorescence LED raw {raw}",
            lambda: self.proxy.sig.fluorescence_ctrl(raw),
        )
        logger.info(
            f"Portable Dropbot fluorescence LED raw --> {raw}: "
            f"{'ok' if ok and result else 'FAILED'}"
        )

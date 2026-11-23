# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json
from datetime import datetime

# Enthought library imports.
from pyface.api import GUI
from traits.api import Instance

# Microdrop package imports.
from device_viewer.consts import VolumeEstimateMessage
from microdrop_application.dialogs.pyface_wrapper import error, warning
from portable_dropbot_controller.consts import (
    FLUORESCENCE_LED_RAW_MAX,
    AlarmRaised,
    ChipLockFailed,
    FirmwareVersionsUpdated,
)
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

# Local imports.
from ..consts import (
    ALARM_LOG_LENGTH,
    FAN_DUTY_BITS,
    HEATER_ONOFF_BITS,
    HUMIDITY_SENSOR_DEAD_RAW,
)
from ..models.model import PortableDropbotStatusAndControlsModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def summarize_mechanisms(mechanisms: dict) -> str:
    """One line for the status pane out of the motor board's state
    bytes: only what a user parks their eyes on."""
    if not mechanisms:
        return "-"
    return (
        f"tray:{mechanisms.get('cabin', '-')} "
        f"mag:{mechanisms.get('mag', '-')} "
        f"filter:{mechanisms.get('flu', '-')} "
        f"pogo:{mechanisms.get('lpush', '-')}/"
        f"{mechanisms.get('rpush', '-')}"
    )


def summarize_chip_pad_contacts(contacts):
    """Say which pogo pads touch the chip, from the STATUS chip_on_pad
    contact mask (bit1 left pad, bit2 right pad; bit0 is the debounced
    presence verdict), with the raw mask appended for reference."""
    left, right = bool(contacts & 0b010), bool(contacts & 0b100)

    if left and right:
        summary = "All pogos on chip"
    elif left:
        summary = "Left pogos on chip"
    elif right:
        summary = "Right pogos on chip"
    else:
        summary = "No pogos on chip"

    return f"{summary} ({contacts})"


def format_environment_reading(value, unit):
    """A device temperature or humidity reading, or "n/a" for the 0xFFFF
    the board sends while its humidity sensor is not answering."""

    if round(value * 100) == HUMIDITY_SENSOR_DEAD_RAW:
        return "n/a"

    return f"{value:.2f} {unit}"


def summarize_switched_on(mask, bits):
    """Say which of ``bits`` (name -> bit) a STATUS bitmask has on: the
    fans fan_duty commands, the heater loops temp_onoff runs."""
    names_on = [name for name, bit in bits.items() if int(mask) & bit]

    return f"{', '.join(names_on)} on" if names_on else "Off"


def summarize_heater_loop(current, target):
    """One heater loop's reading and setpoint (°C)."""
    return f"{current:.2f} °C (target {target:.2f})"


def summarize_status_tail(data):
    """The STATUS tail's HV setpoint and faults as the vendor UI words them:
    "n/a" on firmware without the tail, "not set" / "none" when empty."""
    setpoint, faults = data.get("hv_setpoint"), data.get("faults")

    if setpoint is None:
        setpoint_text = "n/a"
    else:
        setpoint_text = "not set" if setpoint == 0 else f"{setpoint:.2f} V"

    if faults is None:
        faults_text = "n/a"
    else:
        faults_text = ", ".join(faults) if faults else "none"

    return setpoint_text, faults_text


class PortableDropbotStatusAndControlsMessageHandler(BaseMessageHandler):
    """Dramatiq message handler for the Portable Dropbot pane.

    Inherits connected/disconnected, realtime_mode_updated,
    protocol_running and display_state from BaseMessageHandler; adds
    the portable status stream, motor summary, and alarms."""

    model = Instance(PortableDropbotStatusAndControlsModel)

    def _on_advanced_mode_change_triggered(self, body):
        self.model.advanced_mode = str(body).lower() == "true"

    def _on_volume_estimate_triggered(self, body):
        """Show the device viewer's live volume readout; it publishes only
        changes above reading noise, so every message is worth showing."""
        self.model.volume_estimate = VolumeEstimateMessage.model_validate_json(body)

    def _on_ports_updated_triggered(self, body):
        ports = [str(port) for port in json.loads(str(body))]
        self.model.available_ports = ports

        if self.model.selected_port not in ports:
            self.model.selected_port = ports[0] if ports else ""

    def _on_status_updated_triggered(self, body):
        data = json.loads(str(body))
        logger.debug(data)

        self.model.chip_inserted = bool(data.get("chip_on_pad", False))

        chip_pad_contacts = data.get("chip_pad_contacts")
        if chip_pad_contacts is not None:
            self.model.chip_pad_status_text = summarize_chip_pad_contacts(
                chip_pad_contacts
            )

        hv_vol, hv_freq = data.get("hv_vol"), data.get("hv_freq")
        if hv_vol is not None:
            self.model.voltage_readback_display = f"{hv_vol:g} V"
        if hv_freq is not None:
            self.model.frequency_display = f"{hv_freq:g} Hz"

        # The Light control drives the fluorescence LED on this
        # instrument, so its readback is flu_led_bright; the
        # illumination LED's own report shows in the board grid.
        # flu_led_bright is the RAW 16-bit setpoint (0-65535) echoed
        # back unscaled — convert to the same % scale the Light
        # setter uses.
        flu_led = data.get("flu_led_bright")
        if flu_led is not None:
            self.model.light_display = (
                f"{flu_led / FLUORESCENCE_LED_RAW_MAX * 100:.0f} %"
            )

        illumination = data.get("light_led_bright")
        if illumination is not None:
            self.model.illumination_display = f"{illumination:g}"

        chip_cap = data.get("chip_cap")
        if chip_cap is not None:
            self.model.capacitance_display = f"{chip_cap:g} pF"

        # Environment: temperatures, humidity, and the heater/fan
        # loop that regulates them.
        current, target = data.get("cur_temp"), data.get("target_temp")
        if current is not None and target is not None:
            self.model.chip_temp_display = summarize_heater_loop(current, target)

        # Heater channel 1 rides in the STATUS tail (MCU 1.0.1.33+).
        current1, target1 = data.get("cur_temp1"), data.get("target_temp1")
        self.model.heater2_temp_display = (
            "n/a"
            if current1 is None or target1 is None
            else summarize_heater_loop(current1, target1)
        )

        out_power1 = data.get("out_power1")
        self.model.heater2_power_display = (
            "n/a" if out_power1 is None else f"{out_power1:g} %"
        )

        dev_temp = data.get("dev_temp")
        if dev_temp is not None:
            self.model.device_temp_display = format_environment_reading(dev_temp, "°C")

        dev_hum = data.get("dev_hum")
        if dev_hum is not None:
            self.model.device_humidity_display = format_environment_reading(
                dev_hum, "%RH"
            )

        out_power = data.get("out_power")
        if out_power is not None:
            self.model.out_power_display = f"{out_power:g} %"

        heater_on = data.get("temp_onoff")
        if heater_on is not None:
            self.model.heater_on_display = summarize_switched_on(
                heater_on, HEATER_ONOFF_BITS
            )

        fan_duty = data.get("fan_duty")
        if fan_duty is not None:
            self.model.fan_duty_display = summarize_switched_on(fan_duty, FAN_DUTY_BITS)

        # Board health: the firmware halt latch and the STATUS tail.
        halted = data.get("halted")
        if halted is not None:
            self.model.halted = bool(halted)

        self.model.hv_setpoint_display, self.model.faults_display = (
            summarize_status_tail(data)
        )

        # Board diagnostics: the chip health flags.
        chip_short = data.get("chip_short_circuit")
        if chip_short is not None:
            self.model.chip_short_display = "Yes" if chip_short else "No"

        chip_res = data.get("chip_res")
        if chip_res is not None:
            self.model.chip_res_display = f"{chip_res:g}"

        cap_match = data.get("cap_match")
        if cap_match is not None:
            self.model.cap_match_display = f"{cap_match:g}"

    def _on_motors_updated_triggered(self, body):
        data = json.loads(str(body))
        mechanisms = data.get("mechanisms", {})
        self.model.mechanisms_display = summarize_mechanisms(mechanisms)

        if mechanisms:
            # State-byte vocabulary mirrors the ctrl commands (see the
            # motors mixin): cabin 1 = out, mag 1 = engaged, and the
            # pogo pads report 1 while pressed (chip locked).
            self.model.tray_out_reported = mechanisms.get("cabin") == 1
            self.model.magnet_engaged_reported = mechanisms.get("mag") == 1
            # lpush/rpush are not known to follow a smart engage, so the
            # backend reports that separately.
            self.model.chip_locked_reported = data.get("pads_smart_engaged", False) or (
                mechanisms.get("lpush") == 1 and mechanisms.get("rpush") == 1
            )

    def _on_alarm_triggered(self, body):
        """One REPORT_ALARM frame: a raise adds its code to the active
        alarms and the log; a clear (active 0) retires the code and is
        logged as a clear, never as a new alarm."""
        alarm = AlarmRaised.model_validate_json(str(body))

        if not alarm.reports:
            # A backend without the report fields: display strings only.
            if alarm.alarms:
                self._record_alarm("; ".join(alarm.alarms))

            return

        for report in alarm.reports:
            if report.active == 0:
                if report.code:
                    self.model.active_alarms.pop(report.code, None)

                self._log_alarm(f"Cleared: {report.text}")
                continue

            if report.code:
                self.model.active_alarms[report.code] = report.title or report.text

            self._record_alarm(report.text)

    def _on_firmware_versions_updated_triggered(self, body):
        """Show the boards' firmware; firmware below the driver's minimum
        gets a warning once per connect (the backend publishes once). The
        update itself is the vendor UI's job — MicroDrop never flashes."""
        firmware = FirmwareVersionsUpdated.model_validate_json(str(body))
        self.model.firmware_display = (
            f"MCU {firmware.mcu or 'unknown'}, Motor {firmware.motor or 'unknown'}"
        )

        if not firmware.outdated:
            return

        self._record_alarm(f"Firmware outdated: {'; '.join(firmware.outdated)}")
        GUI.invoke_later(
            warning,
            None,
            "The Portable DropBot firmware is older than this driver supports:\n\n"
            + "\n".join(firmware.outdated)
            + "\n\nUpdate it from the Firmware tab of the vendor's DropBot "
            "Portable UI. MicroDrop does not flash firmware.",
            title="Portable DropBot Firmware Outdated",
            cancel=False,
        )

    def _on_error_triggered(self, body):
        data = json.loads(str(body))
        self._record_alarm(
            f"{data.get('context', 'operation')}: {data.get('error', 'failed')}"
        )

    def _on_chip_lock_failed_triggered(self, body):
        """Tell the operator a smart lock or pad retract failed, and put the
        lock toggle back on the reported state."""
        failure = ChipLockFailed.model_validate_json(body)
        message = f"Chip {failure.action} failed: {failure.error}."

        self._record_alarm(message)
        self.model.chip_locked = self.model.chip_locked_reported

        if failure.pads_may_be_pressed:
            GUI.invoke_later(
                warning,
                None,
                f"{message}\n\nThe pogo pads may still be pressing the chip. Check "
                "the instrument, then unlock the chip to retract them once it is "
                "safe.",
                title="Chip Pads May Still Be Pressed",
                cancel=False,
            )
        else:
            GUI.invoke_later(error, None, message, title="Chip Lock Failed")

    def _record_alarm(self, text):
        """Show text as the last alarm and log it."""
        self.model.last_alarm = text
        self._log_alarm(text)

    def _log_alarm(self, text):
        """Push text, timestamped, onto the top of the alarm log, which
        keeps the newest ALARM_LOG_LENGTH."""
        entries = [f"{datetime.now():%H:%M:%S} {text}"]

        if self.model.alarm_log != "-":
            entries += self.model.alarm_log.splitlines()

        self.model.alarm_log = "\n".join(entries[:ALARM_LOG_LENGTH])

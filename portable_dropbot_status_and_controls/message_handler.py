import json

from traits.api import Instance

from logger.logger_service import get_logger
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

from .consts import RGY_STATE_NAMES
from .model import PortableDropbotStatusAndControlsModel

logger = get_logger(__name__)


def summarize_mechanisms(mechanisms: dict) -> str:
    """One line for the status pane out of the motor board's state
    bytes: only what a user parks their eyes on."""
    if not mechanisms:
        return "-"
    return (f"tray:{mechanisms.get('cabin', '-')} "
            f"mag:{mechanisms.get('mag', '-')} "
            f"filter:{mechanisms.get('flu', '-')} "
            f"pogo:{mechanisms.get('lpush', '-')}/"
            f"{mechanisms.get('rpush', '-')}")


class PortableDropbotStatusAndControlsMessageHandler(BaseMessageHandler):
    """Dramatiq message handler for the Portable Dropbot pane.

    Inherits connected/disconnected, realtime_mode_updated,
    protocol_running and display_state from BaseMessageHandler; adds
    the portable status stream, motor summary, and alarms."""

    model = Instance(PortableDropbotStatusAndControlsModel)

    def _on_ports_updated_triggered(self, body):
        ports = [str(port) for port in json.loads(str(body))]
        self.model.available_ports = ports
        if self.model.selected_port not in ports:
            self.model.selected_port = ports[0] if ports else ""

    def _on_status_updated_triggered(self, body):
        data = json.loads(str(body))
        self.model.chip_inserted = bool(data.get("chip_on_pad", False))
        hv_vol, hv_freq = data.get("hv_vol"), data.get("hv_freq")
        if hv_vol is not None:
            self.model.voltage_readback_display = f"{hv_vol:g} V"
        if hv_freq is not None:
            self.model.frequency_display = f"{hv_freq:g} Hz"
        light = data.get("light_led_bright")
        if light is not None:
            self.model.light_display = f"{light:g} %"
        chip_cap = data.get("chip_cap")
        if chip_cap is not None:
            self.model.capacitance_display = f"{chip_cap:g} pF"
        current, target = data.get("cur_temp"), data.get("target_temp")
        if current is not None and target is not None:
            self.model.chip_temp_display = (f"{current:.2f} °C "
                                            f"(target {target:.2f})")
        dev_temp = data.get("dev_temp")
        if dev_temp is not None:
            self.model.device_temp_display = f"{dev_temp:.2f} °C"
        dev_hum = data.get("dev_hum")
        if dev_hum is not None:
            self.model.device_humidity_display = f"{dev_hum:.2f} %RH"
        out_power = data.get("out_power")
        if out_power is not None:
            self.model.out_power_display = f"{out_power:g} %"
        heater_on = data.get("temp_onoff")
        if heater_on is not None:
            self.model.heater_on_display = "On" if heater_on else "Off"
        fan_duty = data.get("fan_duty")
        if fan_duty is not None:
            self.model.fan_duty_display = f"{fan_duty:g} %"
        rgy_state = data.get("rgy_state")
        if rgy_state is not None:
            self.model.rgy_led_display = RGY_STATE_NAMES.get(
                rgy_state, str(rgy_state))
        flu_led = data.get("flu_led_bright")
        if flu_led is not None:
            self.model.flu_led_display = f"{flu_led:g} ‰"
        pmt = data.get("pmt")
        if pmt is not None:
            self.model.pmt_display = f"{pmt:g}"
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
        self.model.mechanisms_display = summarize_mechanisms(
            data.get("mechanisms", {}))

    def _on_alarm_triggered(self, body):
        data = json.loads(str(body))
        alarms = data.get("alarms", [])
        if alarms:
            self.model.last_alarm = "; ".join(str(alarm)
                                              for alarm in alarms)

    def _on_error_triggered(self, body):
        data = json.loads(str(body))
        self.model.last_alarm = (f"{data.get('context', 'operation')}: "
                                 f"{data.get('error', 'failed')}")

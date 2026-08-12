import json

from traits.api import Instance

from logger.logger_service import get_logger
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

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

    def _on_status_updated_triggered(self, body):
        data = json.loads(str(body))
        self.model.chip_inserted = bool(data.get("chip_on_pad", False))
        hv_vol, hv_freq = data.get("hv_vol"), data.get("hv_freq")
        if hv_vol is not None and hv_freq is not None:
            self.model.hv_readback_display = (f"{hv_vol:g} V @ "
                                              f"{hv_freq:g} Hz")
        chip_cap = data.get("chip_cap")
        if chip_cap is not None:
            self.model.capacitance_display = f"{chip_cap:g}"
        current, target = data.get("cur_temp"), data.get("target_temp")
        if current is not None and target is not None:
            self.model.temperature_display = (f"{current:.2f} °C "
                                              f"(target {target:.2f})")

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

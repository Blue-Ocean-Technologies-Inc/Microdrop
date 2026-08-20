import json

from traits.api import Instance

from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

from ..models.pmt_model import PortableDropbotPmtModel


class PortableDropbotPmtMessageHandler(BaseMessageHandler):
    """Connection greying (inherited) plus the PMT_UPDATED stream:
    actual power state and acquire outcomes."""

    model = Instance(PortableDropbotPmtModel)

    def _on_pmt_updated_triggered(self, body):
        data = json.loads(str(body))
        if "power" in data:
            self.model.pmt_power = bool(data["power"])
        if "acquiring" in data:
            self.model.acquiring = bool(data["acquiring"])
        if "acquired_packets" in data:
            packets = data["acquired_packets"]
            self.model.pmt_status_display = (
                f"Acquired {packets} packets" if packets is not None
                else "Acquire FAILED — see log")

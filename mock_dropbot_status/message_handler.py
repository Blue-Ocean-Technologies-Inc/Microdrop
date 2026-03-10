import json

from traits.api import Instance

from logger.logger_service import get_logger
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value

from template_status_and_controls.base_message_handler import BaseMessageHandler

from .consts import listener_name
from .model import MockDropbotStatusModel

logger = get_logger(__name__)


class MockDropbotMessageHandler(BaseMessageHandler):
    """Dramatiq message handler for the MockDropBot status dock pane."""

    model = Instance(MockDropbotStatusModel)
    chip_inserted_message = Instance(TimestampedMessage)

    def _chip_inserted_message_default(self):
        return TimestampedMessage("", 0)

    @timestamped_value("chip_inserted_message")
    def _on_chip_inserted_triggered(self, body):
        inserted = body == "True"
        logger.debug(f"Mock status: Chip inserted -> {inserted}")
        self.model.chip_inserted = inserted

    def _on_capacitance_updated_triggered(self, body):
        if not self.model.realtime_mode:
            return
        data = json.loads(body)
        self.model.capacitance_display = data.get("capacitance", "-")
        self.model.voltage_display = data.get("voltage", "-")

    def _on_halted_triggered(self, message_str):
        data = json.loads(message_str)
        if data.get("name") == "output-current-exceeded":
            self.model.halted = True

    def _on_drops_detected_triggered(self, body):
        data = json.loads(body)
        channels = data.get("detected_channels", [])
        logger.info(f"Mock status: Drops detected on channels {channels}")

    def _on_shorts_detected_triggered(self, body):
        data = json.loads(body)
        shorts = data.get("Shorts_detected", [])
        logger.info(f"Mock status: Shorts on channels {shorts}")

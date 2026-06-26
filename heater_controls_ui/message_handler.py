import json

from traits.api import Instance

from template_status_and_controls.base_message_handler import BaseMessageHandler
from logger.logger_service import get_logger

from .model import HeaterStatusModel
from .telemetry import resolve_selection, format_telemetry

logger = get_logger(__name__)

# ERR kinds that mean the board stopped driving the heater → reflect as halted.
HALTING_ERR_KINDS = ("overtemp", "task_crash", "sensor_fail")


class HeaterMessageHandler(BaseMessageHandler):
    """Dramatiq message handler for the heater UI.

    Inherits the common connected / disconnected handlers from BaseMessageHandler.
    Adds heater-specific handlers for the available-heaters list and telemetry.
    """

    model = Instance(HeaterStatusModel)

    def _on_heaters_available_triggered(self, body):
        try:
            heaters = json.loads(body)
        except Exception:
            return
        if not isinstance(heaters, list):
            return
        self.model.available_heaters = list(heaters)
        self.model.trait_set(**resolve_selection(self.model.selected_heater, heaters))

    def _on_telemetry_triggered(self, body):
        try:
            data = json.loads(body)
        except Exception:
            return
        if not isinstance(data, dict):
            return

        updates = format_telemetry(data)
        if updates:
            self.model.trait_set(**updates)

        if data.get("_frame") == "ERR" and data.get("kind") in HALTING_ERR_KINDS:
            self.model.halted = True

import json

from traits.api import Instance

from logger.logger_service import get_logger
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

from .motors_model import PortableDropbotMotorsModel

logger = get_logger(__name__)


class PortableDropbotMotorsMessageHandler(BaseMessageHandler):
    """Feeds motors_updated signals into the motor panel's model.
    Connection handling is inherited, so the panel greys out with the
    device."""

    model = Instance(PortableDropbotMotorsModel)

    def _on_motors_updated_triggered(self, body):
        data = json.loads(str(body))
        mechanisms = data.get("mechanisms", {})
        if mechanisms:
            self.model.tray_state = str(mechanisms.get("cabin", "-"))
            self.model.magnet_state = str(mechanisms.get("mag", "-"))
            self.model.filter_state = str(mechanisms.get("flu", "-"))
            self.model.pogo_state = (f"{mechanisms.get('lpush', '-')}/"
                                     f"{mechanisms.get('rpush', '-')}")
        positions = data.get("positions", {})
        if positions:
            self.model.positions_display = "  ".join(
                f"{name}:{position}"
                for name, position in positions.items())
        homed = data.get("homed", {})
        if homed:
            homed_names = [name for name, flag in homed.items() if flag]
            self.model.homed_display = (", ".join(homed_names)
                                        if homed_names else "none")

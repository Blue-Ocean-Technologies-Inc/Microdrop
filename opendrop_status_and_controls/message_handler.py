import json

from traits.api import Instance

from template_status_and_controls.base_message_handler import BaseMessageHandler
from logger.logger_service import get_logger

from .model import OpendropStatusAndControlsModel

logger = get_logger(__name__)


class OpendropStatusAndControlsMessageHandler(BaseMessageHandler):
    """Dramatiq message handler for OpenDrop status and controls.

    Inherits common handlers from BaseMessageHandler:
      - connected / disconnected
      - realtime_mode_updated
      - protocol_running
      - display_state

    Adds OpenDrop-specific handlers for board info, temperatures, and feedback.
    """

    # Narrow the type for IDE support and runtime type checking.
    model = Instance(OpendropStatusAndControlsModel)

    # ------------------------------------------------------------------ #
    # OpenDrop-specific handlers                                           #
    # ------------------------------------------------------------------ #

    def _on_board_info_triggered(self, body):
        data = json.loads(str(body))
        self.model.board_id = str(data.get("board_id", "-"))

    def _on_temperatures_updated_triggered(self, body):
        data = json.loads(str(body))
        t1, t2, t3 = data.get("t1"), data.get("t2"), data.get("t3")
        self.model.temperature_1 = "-" if t1 is None else f"{float(t1):.3f} C"
        self.model.temperature_2 = "-" if t2 is None else f"{float(t2):.3f} C"
        self.model.temperature_3 = "-" if t3 is None else f"{float(t3):.3f} C"

    def _on_feedback_updated_triggered(self, body):
        data = json.loads(str(body))
        self.model.feedback_active_channels = str(data.get("active_channels", "-"))

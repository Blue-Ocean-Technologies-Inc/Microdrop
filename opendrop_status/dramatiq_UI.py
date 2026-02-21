import json

from PySide6.QtWidgets import QWidget
from traits.api import HasTraits, Instance

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from opendrop_controller.consts import RETRY_CONNECTION

from .model import OpenDropStatusModel

logger = get_logger(__name__)


class DramatiqOpenDropStatusViewModel(HasTraits):
    model = Instance(OpenDropStatusModel)

    def request_retry_connection(self):
        logger.info("Retrying OpenDrop connection...")
        publish_message("Retry connection button triggered", RETRY_CONNECTION)

    def _on_disconnected_triggered(self, body):
        self.model.connected = False
        self.model.reset_readings()

    def _on_connected_triggered(self, body):
        self.model.connected = True

    def _on_board_info_triggered(self, body):
        data = json.loads(str(body))
        self.model.board_id = str(data.get("board_id", "-"))

    def _on_temperatures_updated_triggered(self, body):
        data = json.loads(str(body))
        t1 = data.get("t1")
        t2 = data.get("t2")
        t3 = data.get("t3")

        self.model.temperature_1 = "-" if t1 is None else f"{float(t1):.3f} C"
        self.model.temperature_2 = "-" if t2 is None else f"{float(t2):.3f} C"
        self.model.temperature_3 = "-" if t3 is None else f"{float(t3):.3f} C"

    def _on_feedback_updated_triggered(self, body):
        data = json.loads(str(body))
        active_channels = data.get("active_channels", "-")
        self.model.feedback_active_channels = str(active_channels)

    def _on_realtime_mode_updated_triggered(self, body):
        if str(body) == "False":
            self.model.reset_readings()


class DramatiqOpenDropStatusView(QWidget):
    """Placeholder view for future OpenDrop status dialogs."""

    def __init__(self, view_model: DramatiqOpenDropStatusViewModel, parent=None):
        super().__init__(parent)
        self.view_model = view_model

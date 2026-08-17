from traits.api import Instance

from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

from .power_system_model import PortableDropbotPowerSystemModel


class PortableDropbotPowerSystemMessageHandler(BaseMessageHandler):
    """Connection greying (inherited) plus the Advanced Mode toggle
    that unlocks the pane."""

    model = Instance(PortableDropbotPowerSystemModel)

    def _on_advanced_mode_change_triggered(self, body):
        self.model.advanced_mode = str(body).lower() == "true"

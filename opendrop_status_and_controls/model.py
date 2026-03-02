from traits.api import HasTraits, Bool, observe, Str

from dropbot_status_and_controls.consts import (
    connected_color,
    connected_no_device_color,
    disconnected_color,
)
from logger.logger_service import get_logger
from opendrop_status.consts import OPENDROP_IMAGE

logger = get_logger(__name__)


class OpendropStatusAndControlsModel(HasTraits):
    """Unified model for  status display and manual controls."""

    realtime_mode = Bool(False, desc="Enable or disable realtime mode")

    # Status (read-only, updated by message handler)
    connected = Bool(False, desc="True if the DropBot is connected")
    chip_inserted = Bool(False, desc="True if a chip is inserted")

    icon_path = Str(OPENDROP_IMAGE)
    icon_color = Str(disconnected_color)
    connection_status_text = Str("Inactive")

    board_id = Str("-", desc="OpenDrop board identifier")
    temperature_1 = Str("-", desc="Temperature channel 1 in C")
    temperature_2 = Str("-", desc="Temperature channel 2 in C")
    temperature_3 = Str("-", desc="Temperature channel 3 in C")
    feedback_active_channels = Str("-", desc="Number of active feedback channels")

    def _update_icon_color(self):
        if self.connected:
            if self.chip_inserted:
                self.icon_color = connected_color
            else:
                self.icon_color = connected_no_device_color
        else:
            self.icon_color = disconnected_color

    @observe("connected")
    def _update_connection_display(self, event):
        self.connection_status_text = "Active" if self.connected else "Inactive"
        self._update_icon_color()

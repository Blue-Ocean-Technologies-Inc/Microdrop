from traits.api import HasTraits, Range, Bool, Str, observe

from dropbot_controller.preferences import DropbotPreferences
from logger.logger_service import get_logger
from microdrop_utils.ureg_helpers import trim_to_n_digits

from .consts import (
    DROPBOT_IMAGE, DROPBOT_CHIP_INSERTED_IMAGE,
    disconnected_color, connected_no_device_color, connected_color,
)

logger = get_logger(__name__)

N_DISPLAY_DIGITS = 3


class DropbotStatusAndControlsModel(HasTraits):
    """Unified model for DropBot status display and manual controls."""

    # Controls (user-writable via TraitsUI)
    voltage = Range(
        30, 150, value=DropbotPreferences().default_voltage,
        desc="the voltage to set on the dropbot device (V)"
    )
    frequency = Range(
        100, 20000, value=DropbotPreferences().default_frequency,
        desc="the frequency to set on the dropbot device (Hz)"
    )
    realtime_mode = Bool(False, desc="Enable or disable realtime mode")

    # Status (read-only, updated by message handler)
    connected = Bool(False, desc="True if the DropBot is connected")
    chip_inserted = Bool(False, desc="True if a chip is inserted")

    # Sensor readings (display strings)
    capacitance = Str("-", desc="Raw capacitance in pF")
    voltage_readback = Str("-", desc="Voltage readback from device in V")
    pressure = Str("-", desc="Pressure reading in pF/mm^2")
    force = Str("-", desc="Calculated force in N")

    # Computed display traits (derived from connected / chip_inserted / readings)
    connection_status_text = Str("Inactive")
    chip_status_text = Str("Not Inserted")
    icon_path = Str(DROPBOT_IMAGE)
    icon_color = Str(disconnected_color)

    # Formatted sensor readings for display
    capacitance_display = Str("-")
    voltage_readback_display = Str("-")
    pressure_display = Str("-")
    force_display = Str("-")

    def reset_readings(self):
        """Reset sensor reading displays."""
        self.capacitance = "-"
        self.voltage_readback = "-"
        self.pressure = "-"
        self.force = "-"

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

    @observe("chip_inserted")
    def _update_chip_display(self, event):
        self.chip_status_text = "Inserted" if self.chip_inserted else "Not Inserted"
        self.icon_path = DROPBOT_CHIP_INSERTED_IMAGE if self.chip_inserted else DROPBOT_IMAGE
        self._update_icon_color()

    @observe("capacitance")
    def _update_capacitance_display(self, event):
        self.capacitance_display = self._format_reading(event.new)

    @observe("voltage_readback")
    def _update_voltage_readback_display(self, event):
        self.voltage_readback_display = self._format_reading(event.new)

    @observe("pressure")
    def _update_pressure_display(self, event):
        self.pressure_display = self._format_reading(event.new)

    @observe("force")
    def _update_force_display(self, event):
        self.force_display = self._format_reading(event.new)

    @staticmethod
    def _format_reading(value):
        try:
            return trim_to_n_digits(value, N_DISPLAY_DIGITS)
        except AssertionError:
            if value == "-":
                return value
            else:
                logger.warning(f"Cannot parse reading: '{value}'. Expected format: '[quantity] [units]'")
                return "-"

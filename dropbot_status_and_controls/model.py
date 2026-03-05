from traits.api import Bool, Str, observe

from dropbot_controller.consts import VOLTAGE_LIM, FREQUENCY_LIM
from dropbot_controller.preferences import DropbotPreferences
from logger.logger_service import get_logger
from microdrop_utils.ureg_helpers import trim_to_n_digits, ureg

from template_status_and_controls.base_model import BaseStatusModel

from .consts import (
    DROPBOT_IMAGE, DROPBOT_CHIP_INSERTED_IMAGE,
    disconnected_color, connected_no_device_color, connected_color,
)
from .view_helpers import RangeWithCustomViewHints

logger = get_logger(__name__)

N_DISPLAY_DIGITS = 3


class DropbotStatusAndControlsModel(BaseStatusModel):
    """Model for DropBot status display and controls.

    Extends BaseStatusModel with DropBot-specific controls and sensor readings.
    Connection/mode/icon traits and their observers are inherited.
    """

    # ---- Class-level constants ----------------------------------------
    DEFAULT_ICON_PATH = DROPBOT_IMAGE
    CHIP_INSERTED_ICON_PATH = DROPBOT_CHIP_INSERTED_IMAGE
    DISCONNECTED_COLOR = disconnected_color
    CONNECTED_NO_DEVICE_COLOR = connected_no_device_color
    CONNECTED_COLOR = connected_color

    # ---- Hardware controls (user-writable via UI) ----------------------
    voltage = RangeWithCustomViewHints(
        VOLTAGE_LIM[0],
        VOLTAGE_LIM[1],
        step=5,
        suffix=" V",
        value=DropbotPreferences().default_voltage,  # TODO: May need to give as input application preferences.
        desc="the voltage to set on the dropbot device (V)",
    )
    frequency = RangeWithCustomViewHints(
        FREQUENCY_LIM[0],
        FREQUENCY_LIM[1],
        step=100,
        suffix=" Hz",
        value=DropbotPreferences().default_frequency,  # TODO: May need to give as input application preferences.
        desc="the frequency to set on the dropbot device (Hz)",
    )

    # ---- Device-specific status ----------------------------------------
    chip_status_text = Str("Not Inserted")

    # ---- Sensor readings (raw values set by message handler) -----------
    capacitance = Str("-", desc="Raw capacitance in pF")
    voltage_readback = Str("-", desc="Voltage readback from device (V)")
    pressure = Str("-", desc="Pressure reading (pF/mm²)")
    force = Str("-", desc="Calculated force (N)")

    # ---- Formatted sensor readings for display -------------------------
    capacitance_display = Str("-")
    voltage_readback_display = Str("-")
    frequency_display = Str("-")
    pressure_display = Str("-")
    force_display = Str("-")

    # ------------------------------------------------------------------ #
    # BaseStatusModel hook                                                 #
    # ------------------------------------------------------------------ #

    def _update_chip_display(self, inserted: bool) -> None:
        self.chip_status_text = "Inserted" if inserted else "Not Inserted"

    # ------------------------------------------------------------------ #
    # Observers                                                            #
    # ------------------------------------------------------------------ #

    @observe("realtime_mode")
    def _reset_readings_on_realtime_off(self, event):
        """Clear sensor displays when realtime mode is disabled."""
        if not event.new:
            self.capacitance = "-"
            self.voltage_readback = "-"
            self.frequency_display = "-"
            self.pressure = "-"
            self.force = "-"

    @observe("capacitance")
    def _update_capacitance_display(self, event):
        self.capacitance_display = self._format_reading(event.new)

    @observe("voltage_readback")
    def _update_voltage_readback_display(self, event):
        self.voltage_readback_display = self._format_reading(event.new)

    @observe("frequency,realtime_mode")
    def _update_frequency_display(self, event):
        if self.realtime_mode:
            self.frequency_display = self._format_reading(f"{self.frequency} Hz")

    @observe("pressure")
    def _update_pressure_display(self, event):
        self.pressure_display = self._format_reading(event.new)

    @observe("force")
    def _update_force_display(self, event):
        self.force_display = self._format_reading(event.new)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_reading(value):
        try:
            return trim_to_n_digits(ureg.Quantity(value).to_compact(), N_DISPLAY_DIGITS)
        except AssertionError:
            if value == "-":
                return value
            logger.warning(f"Cannot parse reading: '{value}'. Expected '[quantity] [units]'")
            return "-"

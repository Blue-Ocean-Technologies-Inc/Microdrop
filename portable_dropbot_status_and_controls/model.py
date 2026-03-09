from dropbot_status_and_controls.model import DropbotStatusAndControlsModel
from traits.api import Bool, Str, observe

from dropbot_status_and_controls.view_helpers import RangeWithCustomViewHints
from logger.logger_service import get_logger
from microdrop_utils.ureg_helpers import trim_to_n_digits

from .consts import (
    DROPBOT_IMAGE,
    DROPBOT_CHIP_INSERTED_IMAGE,
    VOLTAGE_LIM,
    FREQUENCY_LIM,
)

logger = get_logger(__name__)

N_DISPLAY_DIGITS = 3


class PortableDropbotStatusAndControlsModel(DropbotStatusAndControlsModel):
    """Model for Portable DropBot status display.

    Extends BaseStatusModel with portable-specific sensor readings.
    Connection/mode/icon traits and their observers are inherited.
    """

    # ---- Class-level constants ----------------------------------------
    DEFAULT_ICON_PATH = DROPBOT_IMAGE
    CHIP_INSERTED_ICON_PATH = DROPBOT_CHIP_INSERTED_IMAGE

    # ---- Device-specific status ----------------------------------------
    chip_status_text = Str("Not Inserted")
    tray_operation_failed = Bool(
        False, desc="True when tray toggle failed, triggers icon re-enable"
    )

    # ---- Hardware controls (user-writable via UI) Change limits for Portable----------------------
    voltage = RangeWithCustomViewHints(
        VOLTAGE_LIM[0],
        VOLTAGE_LIM[1],
        step=5,
        suffix=" V",
        # value=DropbotPreferences().default_voltage,  # TODO: May need to give as input application preferences.
        desc="the voltage to set on the dropbot device (V)",
    )
    frequency = RangeWithCustomViewHints(
        FREQUENCY_LIM[0],
        FREQUENCY_LIM[1],
        step=100,
        suffix=" Hz",
        # value=DropbotPreferences().default_frequency,  # TODO: May need to give as input application preferences.
        desc="the frequency to set on the dropbot device (Hz)",
    )

    ########################################################################
    # Extra Portable Specific
    ########################################################################

    # ---- Sensor readings (set by message handler) ----------------------
    zstage_position = Str("-", desc="Zstage height in mm")
    device_humidity = Str("-", desc="Humidity in %")
    chip_temp = Str("-", desc="Chip temperature in C")
    device_temp = Str("-", desc="Device temperature in C")

    # ---- Formatted display traits --------------------------------------
    zstage_position_display = Str("-")
    device_humidity_display = Str("-")
    device_temp_display = Str("-")
    chip_temp_display = Str("-")

    # ---- Observers -----------------------------------------------------

    @observe("realtime_mode")
    def _reset_readings_on_realtime_off(self, event):
        """Clear sensor displays when realtime mode is disabled."""
        if not event.new:
            self.capacitance = self.voltage = self.frequency = self.chip_temp = self.device_temp = self.zstage_position = self.device_humidity = "-"

    @observe("zstage_position")
    def _update_zstage_position_display(self, event):
        self.zstage_position_display = self._format_reading(event.new)

    @observe("chip_temp")
    def _update_chip_temp_display(self, event):
        self.chip_temp_display = self._format_reading(event.new)

    @observe("device_temp")
    def _update_device_temp_display(self, event):
        self.device_temp_display = self._format_reading(event.new)

    @observe("device_humidity")
    def _update_device_humidity_display(self, event):
        self.device_humidity_display = self._format_reading(event.new)

    # ---- Helpers -------------------------------------------------------

    @staticmethod
    def _format_reading(value):
        try:
            return trim_to_n_digits(value, N_DISPLAY_DIGITS)
        except AssertionError:
            if value == "-":
                return value
            logger.warning(
                f"Cannot parse reading: '{value}'. "
                "Expected '[quantity] [units]'"
            )
            return "-"

from dropbot_status_and_controls.model import DropbotStatusAndControlsModel
from traits.api import Bool, Str, observe

from logger.logger_service import get_logger
from microdrop_utils.ureg_helpers import trim_to_n_digits

from .consts import DROPBOT_IMAGE, DROPBOT_CHIP_INSERTED_IMAGE

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

    # ---- Sensor readings (set by message handler) ----------------------
    capacitance = Str("-", desc="Raw capacitance in pF")
    voltage = Str("-", desc="Voltage set to device in V")
    frequency = Str("-", desc="Frequency of chip in Hz")
    zstage_position = Str("-", desc="Zstage height in mm")
    device_humidity = Str("-", desc="Humidity in %")
    chip_temp = Str("-", desc="Chip temperature in C")
    device_temp = Str("-", desc="Device temperature in C")

    # ---- Formatted display traits --------------------------------------
    capacitance_display = Str("-")
    voltage_display = Str("-")
    frequency_display = Str("-")
    zstage_position_display = Str("-")
    device_humidity_display = Str("-")
    device_temp_display = Str("-")
    chip_temp_display = Str("-")

    # ---- BaseStatusModel hook ------------------------------------------

    def _update_chip_display(self, inserted: bool) -> None:
        self.chip_status_text = "Inserted" if inserted else "Not Inserted"

    # ---- Observers -----------------------------------------------------

    @observe("realtime_mode")
    def _reset_readings_on_realtime_off(self, event):
        """Clear sensor displays when realtime mode is disabled."""
        if not event.new:
            self.capacitance = "-"
            self.voltage = "-"
            self.frequency = "-"
            self.device_humidity = "-"

    @observe("capacitance")
    def _update_capacitance_display(self, event):
        self.capacitance_display = self._format_reading(event.new)

    @observe("voltage")
    def _update_voltage_display(self, event):
        self.voltage_display = self._format_reading(event.new)

    @observe("frequency")
    def _update_frequency_display(self, event):
        self.frequency_display = self._format_reading(event.new)

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

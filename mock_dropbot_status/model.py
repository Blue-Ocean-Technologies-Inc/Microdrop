from traits.api import Bool, Str, Float, Int, observe, Range, Button

from template_status_and_controls.base_model import BaseStatusModel
from microdrop_style.colors import GREY, SUCCESS_COLOR, WARNING_COLOR, ERROR_COLOR

from mock_dropbot_controller.consts import (
    DEFAULT_BASE_CAPACITANCE_PF, DEFAULT_CAPACITANCE_DELTA_PF,
    DEFAULT_CAPACITANCE_NOISE_PF, DEFAULT_STREAM_INTERVAL_MS,
    HARDWARE_DEFAULT_VOLTAGE, HARDWARE_DEFAULT_FREQUENCY, DEFAULT_NUM_CHANNELS,
)

from logger.logger_service import get_logger
logger = get_logger(__name__)


class MockDropbotStatusModel(BaseStatusModel):
    """Model for the MockDropBot dock pane."""

    DISCONNECTED_COLOR = GREY["lighter"]
    CONNECTED_NO_DEVICE_COLOR = WARNING_COLOR
    CONNECTED_COLOR = SUCCESS_COLOR
    HALTED_COLOR = ERROR_COLOR

    chip_status_text = Str("Not Inserted")
    capacitance_display = Str("-")
    voltage_display = Str("-")
    frequency_display_text = Str("-")

    base_capacitance_pf = Float(DEFAULT_BASE_CAPACITANCE_PF, desc="Base capacitance in pF")
    capacitance_delta_pf = Float(DEFAULT_CAPACITANCE_DELTA_PF, desc="Capacitance added per actuated electrode in pF")
    capacitance_noise_pf = Float(DEFAULT_CAPACITANCE_NOISE_PF, desc="Random noise range in pF")
    stream_interval_ms = Range(50, 5000, value=DEFAULT_STREAM_INTERVAL_MS, desc="Stream publish interval in ms")
    stream_active = Bool(False, desc="Whether capacitance stream is active")

    voltage = Float(HARDWARE_DEFAULT_VOLTAGE)
    frequency = Float(HARDWARE_DEFAULT_FREQUENCY)
    num_channels = Int(DEFAULT_NUM_CHANNELS)

    shorts_channels_text = Str("5, 12, 18", desc="Comma-separated channel indices for simulated shorts")
    simulate_shorts_button = Button("Simulate Shorts")
    halt_error_type = Str("output-current-exceeded")
    simulate_halt_button = Button("Simulate Halt")
    simulate_chip_toggle = Button("Toggle Chip Insert")
    simulate_connect_button = Button("Connect")
    simulate_disconnect_button = Button("Disconnect")

    actuated_channels_text = Str("None")

    def _update_chip_display(self, inserted: bool) -> None:
        self.chip_status_text = "Inserted" if inserted else "Not Inserted"

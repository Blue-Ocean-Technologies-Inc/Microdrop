import json

from traits.api import Instance, List

from PySide6.QtCore import QObject, Signal

from logger.logger_service import get_logger
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.ureg_helpers import (
    ureg,
    ureg_quant_percent_change,
    ureg_diff,
    get_ureg_magnitude,
)

from dropbot_controller.consts import RETRY_CONNECTION
from template_status_and_controls.base_message_handler import BaseMessageHandler

from .consts import NUM_CAPACITANCE_READINGS_AVERAGED
from .model import PortableDropbotStatusAndControlsModel

logger = get_logger(__name__)


def _change_is_significant(old_value, new_value, threshold, threshold_type) -> bool:
    """Return True when the change between two readings exceeds the threshold."""
    if old_value == "-" and new_value != "-":
        return True
    if old_value != "-" and new_value != "-":
        if threshold_type == "percentage":
            change = ureg_quant_percent_change(old=old_value, new=new_value)
        else:  # absolute_diff
            change = abs(ureg_diff(old=old_value, new=new_value))
        return change > threshold
    return False


class DialogSignals(QObject):
    """Qt signals for dialog/popup events, bridging the Dramatiq -> UI thread boundary."""
    show_shorts_popup = Signal(dict)
    show_no_power_dialog = Signal()
    close_no_power_dialog = Signal()
    show_halted_popup = Signal(str)


class PortableDropbotMessageHandler(BaseMessageHandler):
    """Dramatiq message handler for Portable DropBot status and controls.

    Inherits common handlers from BaseMessageHandler:
      - connected / disconnected
      - realtime_mode_updated
      - protocol_running
      - display_state

    Adds portable-specific handlers for board status updates, chip insertion,
    tray failures, z-stage position, and dialog popups.
    """

    model = Instance(PortableDropbotStatusAndControlsModel)
    dialog_signals = Instance(DialogSignals)

    # Deduplication guard for chip-insertion messages.
    chip_inserted_message = Instance(TimestampedMessage)

    # Internal state for capacitance averaging
    _capacitance_buffer = List()
    _no_power = False

    def _chip_inserted_message_default(self):
        return TimestampedMessage("", 0)

    # ---- Publisher ----

    def request_retry_connection(self):
        """Trigger a reconnection attempt (used by the no-power dialog)."""
        logger.info("Retrying Portable DropBot connection")
        publish_message("Retry connection button triggered", RETRY_CONNECTION)
        if self._no_power:
            self._no_power = False
            self.dialog_signals.close_no_power_dialog.emit()

    # ---- Portable-specific handlers ----

    def _on_board_status_update_triggered(self, body):
        """Parse combined board status JSON and update model traits."""
        msg = json.loads(str(body))

        # Receiving board status implies we're connected
        self.model.connected = True

        # -- Capacitance (with averaging + significance check) --
        capacitance = msg.get("chip_cap", "-")
        new_cap = (
            f"{capacitance * ureg.picofarad:.4g~P}" if capacitance != "-" else "-"
        )
        if new_cap != "-":
            self._capacitance_buffer.append(get_ureg_magnitude(new_cap))
            if len(self._capacitance_buffer) == NUM_CAPACITANCE_READINGS_AVERAGED:
                avg = sum(self._capacitance_buffer) / NUM_CAPACITANCE_READINGS_AVERAGED
                new_cap = f"{avg * ureg.picofarad:.4g~P}"
                self._capacitance_buffer = []
            else:
                new_cap = self.model.capacitance  # keep old until buffer full

            if _change_is_significant(
                self.model.capacitance, new_cap, threshold=3, threshold_type="absolute_diff"
            ):
                self.model.capacitance = new_cap

        # -- Voltage --
        voltage = msg.get("hv_vol", "-")
        new_voltage = f"{voltage * ureg.volt:.3g~P}" if voltage != "-" else "-"
        if new_voltage != "-" and _change_is_significant(
            self.model.voltage_readback, new_voltage, threshold=1, threshold_type="absolute_diff"
        ):
            self.model.voltage_readback = new_voltage

        # -- Frequency --
        def _get_formatted(key, unit):
            val = msg.get(key)
            if isinstance(val, (int, float)):
                return ureg.Quantity(val, unit)
            return "-"

        freq = _get_formatted("hv_freq", ureg.hertz)
        self.model.frequency = (
            f"{freq.to_compact():.5g~P}" if freq != "-" else "-"
        )

        # -- Temperatures and humidity --
        self.model.chip_temp = str(_get_formatted("cur_temp", ureg.degC))
        self.model.device_temp = str(_get_formatted("dev_temp", ureg.degC))
        self.model.device_humidity = str(_get_formatted("dev_hum", ureg.percent))

    @timestamped_value("chip_inserted_message")
    def _on_chip_inserted_triggered(self, body):
        content = str(body) if body is not None else ""
        inserted = content.lower() == "true"
        logger.debug(f"Chip inserted -> {inserted}")
        self.model.chip_inserted = inserted

    def _on_tray_toggle_failed_triggered(self, body):
        """Re-enable tray icon when hardware reports tray move failure."""
        self.model.tray_operation_failed = True

    def _on_position_updated_triggered(self, body):
        self.model.zstage_position = f"{body} mm"

    def _on_calibration_data_triggered(self, body):
        """No-op: calibration data is consumed by protocol_grid."""
        pass

    # ---- Dialog handlers ----

    def _on_shorts_detected_triggered(self, shorts_dict):
        data = json.loads(shorts_dict)
        shorts = data.get("Shorts_detected", [])
        show_window = data.get("Show_window", False)

        if not shorts and not show_window:
            logger.info("No shorts detected")
            return

        if shorts:
            title = "Shorts Detected"
            text = (
                f"Shorts detected on channels: [{', '.join(str(s) for s in shorts)}]\n\n"
                "The affected channels are disabled until the DropBot is restarted."
            )
        else:
            title = "No Shorts Detected"
            text = "No shorts were detected on any channels."

        self.dialog_signals.show_shorts_popup.emit({"title": title, "text": text})

    def _on_no_power_triggered(self, body):
        if self._no_power:
            return
        self._no_power = True
        self.dialog_signals.show_no_power_dialog.emit()

    def _on_halted_triggered(self, message_str):
        data = json.loads(message_str)
        text = f"DropBot has halted {data.get('reason')}.\n\n{data.get('message')}"
        self.dialog_signals.show_halted_popup.emit(text)

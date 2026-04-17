import json
import math

from traits.api import Instance, List, Bool

from logger.logger_service import get_logger
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.ureg_helpers import ureg, get_ureg_magnitude

from dropbot_controller.consts import RETRY_CONNECTION

from PySide6.QtCore import QObject, Signal

from template_status_and_controls.base_message_handler import BaseMessageHandler

from .consts import NUM_CAPACITANCE_READINGS_AVERAGED
from .model import DropbotStatusAndControlsModel


class DialogSignals(QObject):
    """Qt signals for dialog/popup events, bridging the Dramatiq → UI thread boundary."""
    show_shorts_popup = Signal(dict)
    show_no_power_dialog = Signal()
    close_no_power_dialog = Signal()
    show_halted_popup = Signal(dict)
    voltage_frequency_range_changed = Signal(dict)

logger = get_logger(__name__)


def _change_is_significant(old_value, new_value, threshold, threshold_type) -> bool:
    """Return True when the change between two pint.Quantity readings exceeds the threshold."""
    old_nan = math.isnan(old_value.magnitude)
    new_nan = math.isnan(new_value.magnitude)

    if old_nan and not new_nan:
        return True
    if not old_nan and not new_nan:
        old_mag = old_value.magnitude
        new_mag = new_value.magnitude
        if threshold_type == "percentage":
            change = 100 * abs(old_mag - new_mag) / old_mag
        else:  # absolute_diff
            change = abs(old_mag - new_mag)
        return change > threshold
    return False


class DropbotStatusAndControlsMessageHandler(BaseMessageHandler):
    """Dramatiq message handler for DropBot status and controls.

    Inherits common handlers from BaseMessageHandler:
      - connected / disconnected (with realtime-mode reset on disconnect)
      - realtime_mode_updated
      - protocol_running
      - display_state

    Adds DropBot-specific handlers for:
      - chip insertion
      - capacitance / voltage readback (with averaging and significance filter)
      - calibration data → c_device / force calculation
      - shorts detected, no-power, halted (all via dialog signals)
    """

    # Narrow model type for IDE support.
    model = Instance(DropbotStatusAndControlsModel)

    # Carries dialog/popup signals across the Dramatiq → Qt thread boundary.
    dialog_signals = Instance(DialogSignals)

    # Deduplication guard for chip-insertion messages.
    chip_inserted_message = Instance(TimestampedMessage)

    # ---- Internal state for capacitance averaging ---------------------
    _capacitance_buffer = List()
    _no_power = Bool(False)

    def _chip_inserted_message_default(self):
        return TimestampedMessage("", 0)

    # ------------------------------------------------------------------ #
    # Publisher                                                            #
    # ------------------------------------------------------------------ #

    def request_retry_connection(self):
        """Trigger a reconnection attempt (used by the no-power dialog)."""
        logger.info("Retrying DropBot connection")
        publish_message("Retry connection button triggered", RETRY_CONNECTION)
        if self._no_power:
            self._no_power = False
            self.dialog_signals.close_no_power_dialog.emit()

    # ------------------------------------------------------------------ #
    # DropBot-specific handlers                                            #
    # ------------------------------------------------------------------ #

    @timestamped_value("chip_inserted_message")
    def _on_chip_inserted_triggered(self, body):
        if body == "True":
            inserted = True
        elif body == "False":
            inserted = False
        else:
            logger.error(f"Invalid chip_inserted value: {body!r}")
            inserted = False
        logger.debug(f"Chip inserted → {inserted}")
        self.model.chip_inserted = inserted

    def _on_capacitance_updated_triggered(self, body):
        if not self.model.realtime_mode:
            return

        data = json.loads(body)
        new_cap_str = data.get("capacitance")
        new_voltage_str = data.get("voltage")

        if not new_cap_str or not new_voltage_str:
            return

        # Accumulate readings; only update the model after averaging N samples.
        self._capacitance_buffer.append(get_ureg_magnitude(new_cap_str))
        if len(self._capacitance_buffer) == NUM_CAPACITANCE_READINGS_AVERAGED:
            avg = sum(self._capacitance_buffer) / NUM_CAPACITANCE_READINGS_AVERAGED
            new_cap = avg * ureg.picofarad
            self._capacitance_buffer = []
        else:
            new_cap = self.model.capacitance  # keep old value until buffer is full

        new_voltage = ureg(new_voltage_str)

        if _change_is_significant(self.model.capacitance, new_cap, threshold=3, threshold_type="absolute_diff"):
            self.model.capacitance = new_cap

        if _change_is_significant(self.model.voltage_readback, new_voltage, threshold=1, threshold_type="absolute_diff"):
            self.model.voltage_readback = new_voltage

    def _on_calibration_data_triggered(self, body_str):
        data = json.loads(body_str)
        filler_cap = data.get("filler_capacitance_over_area")
        liquid_cap = data.get("liquid_capacitance_over_area")

        if filler_cap is not None and liquid_cap is not None:
            c_device_value = liquid_cap - filler_cap
            self.model.c_device = ureg(f"{c_device_value:.4f} pF/mm^2")
        else:
            self.model.c_device = ureg("nan pF/mm^2")

    # def _on_shorts_detected_triggered(self, shorts_dict):
    #     data = json.loads(shorts_dict)
    #     shorts = data.get("Shorts_detected", [])
    #     show_window = data.get("Show_window", False)
    #
    #     if not shorts and not show_window:
    #         logger.info("No shorts detected")
    #         return
    #
    #     if shorts:
    #         title = "Shorts Detected"
    #         text = (
    #             f"Shorts detected on channels: [{', '.join(str(s) for s in shorts)}]\n\n"
    #             "You can disable the affected channels from the Device Viewer."
    #         )
    #     else:
    #         title = "No Shorts Detected"
    #         text = "No shorts were detected on any channels."
    #
    #     self.dialog_signals.show_shorts_popup.emit({"title": title, "text": text})

    def _on_no_power_triggered(self, body):
        if self._no_power:
            return
        self._no_power = True
        self.dialog_signals.show_no_power_dialog.emit()

    def _on_halted_triggered(self, message_str):
        data = json.loads(message_str)
        if data.get('name') == 'output-current-exceeded':
            self.model.halted = True
        reason = data.get('reason', '')
        message = data.get('message', '')
        self.dialog_signals.show_halted_popup.emit({
            'title': 'DropBot Halted',
            'reason': reason,
            'message': message,
        })

    def _on_voltage_frequency_range_changed_triggered(self, message):
        """Update voltage/frequency spinner bounds live when range preferences change.

        Updates the Traits Range validation bounds on the model, then emits a
        Qt signal so the dock pane can update the QSpinBox widgets on the UI thread.
        """
        data = json.loads(message)
        # Signal the UI thread to update the QSpinBox widgets
        self.dialog_signals.voltage_frequency_range_changed.emit(data)
import json

import dramatiq
from traits.api import Instance, List, Bool, Float

from logger.logger_service import get_logger
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.ureg_helpers import ureg, ureg_quant_percent_change, ureg_diff, get_ureg_magnitude

from dropbot_controller.consts import RETRY_CONNECTION
from protocol_grid.services.force_calculation_service import ForceCalculationService

from PySide6.QtCore import QObject, Signal

from template_status_and_controls.base_message_handler import BaseMessageHandler

from .consts import NUM_CAPACITANCE_READINGS_AVERAGED, listener_name
from .model import DropbotStatusAndControlsModel


class DialogSignals(QObject):
    """Qt signals for dialog/popup events, bridging the Dramatiq → UI thread boundary."""
    show_shorts_popup = Signal(dict)
    show_no_power_dialog = Signal()
    close_no_power_dialog = Signal()
    show_halted_popup = Signal(dict)

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
      - calibration data → pressure / force calculation
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
        new_cap = data.get("capacitance", "-")
        new_voltage = data.get("voltage", "-")

        # Accumulate readings; only update the model after averaging N samples.
        self._capacitance_buffer.append(get_ureg_magnitude(new_cap))
        if len(self._capacitance_buffer) == NUM_CAPACITANCE_READINGS_AVERAGED:
            avg = sum(self._capacitance_buffer) / NUM_CAPACITANCE_READINGS_AVERAGED
            new_cap = f"{avg * ureg.picofarad:.4g~P}"
            self._capacitance_buffer = []
        else:
            new_cap = self.model.capacitance  # keep old value until buffer is full

        if _change_is_significant(self.model.capacitance, new_cap, threshold=3, threshold_type="absolute_diff"):
            self.model.capacitance = new_cap

        if _change_is_significant(self.model.voltage_readback, new_voltage, threshold=1, threshold_type="absolute_diff"):
            self.model.voltage_readback = new_voltage
            self._recalculate_force(voltage=get_ureg_magnitude(new_voltage))

    def _on_calibration_data_triggered(self, body_str):
        data = json.loads(body_str)
        filler_cap = data.get("filler_capacitance_over_area")
        liquid_cap = data.get("liquid_capacitance_over_area")

        if filler_cap is not None and liquid_cap is not None:
            pressure = liquid_cap - filler_cap
            self.model.pressure = f"{pressure:.4f} pF/mm^2"
            if self.model.voltage_readback != "-":
                self._recalculate_force(
                    voltage=get_ureg_magnitude(self.model.voltage_readback),
                    pressure=pressure,
                )
            else:
                logger.error("Voltage not available — cannot calculate force. Recalibrate after voltage is set.")
                self.model.force = "-"
        else:
            self.model.pressure = "-"
            self.model.force = "-"

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
        reason = data.get('reason', '')
        message = data.get('message', '')
        self.dialog_signals.show_halted_popup.emit({
            'title': 'DropBot Halted',
            'reason': reason,
            'message': message,
        })

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    def _recalculate_force(self, voltage, pressure=None):
        """Recompute and store the force reading from voltage + pressure."""
        if pressure is None:
            if self.model.pressure == "-":
                return
            pressure = get_ureg_magnitude(self.model.pressure)
        force = ForceCalculationService.calculate_force_for_step(voltage, pressure)
        self.model.force = f"{force:.4f} mN/m" if force is not None else "-"

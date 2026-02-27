import json

import dramatiq
from traits.api import HasTraits, Instance, Str, List, Bool, Float
from PySide6.QtCore import QObject, Signal

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.ureg_helpers import ureg, ureg_quant_percent_change, ureg_diff, get_ureg_magnitude

from dropbot_controller.consts import RETRY_CONNECTION
from protocol_grid.services.force_calculation_service import ForceCalculationService

from .consts import NUM_CAPACITANCE_READINGS_AVERAGED, listener_name
from .model import DropbotStatusAndControlsModel

logger = get_logger(__name__)


def check_change_significance(old_value, new_value, threshold=60, threshold_type='percentage') -> bool:
    if old_value == '-' and new_value != '-':
        return True

    elif old_value != '-' and new_value != '-':
        change = 0

        if threshold_type == 'percentage':
            change = ureg_quant_percent_change(old=old_value, new=new_value)

        elif threshold_type == 'absolute_diff':
            change = abs(ureg_diff(old=old_value, new=new_value))

        if change > threshold:
            return True
    return False


class DialogSignals(QObject):
    """Signals for dialog/popup UI events, ensuring thread safety."""
    show_shorts_popup = Signal(dict)
    show_no_power_dialog = Signal()
    close_no_power_dialog = Signal()
    show_halted_popup = Signal(str)


class DropbotStatusAndControlsMessageHandler(HasTraits):
    """Unified Dramatiq message handler for dropbot status and controls.

    Subscribes to dropbot/signals/# and ui/calibration_data.
    Updates the shared model and emits dialog signals.
    """

    model = Instance(DropbotStatusAndControlsModel)
    dialog_signals = Instance(DialogSignals)

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = Str()

    # TimestampedMessage helpers for deduplication
    realtime_mode_message = Instance(TimestampedMessage)
    connected_message = Instance(TimestampedMessage)
    chip_inserted_message = Instance(TimestampedMessage)

    # Internal state
    capacitances = List()
    no_power = Bool(False)
    filler_capacitance_over_area = Float(0)
    liquid_capacitance_over_area = Float(0)
    pressure_value = Float(0)

    def _realtime_mode_message_default(self):
        return TimestampedMessage("", 0)

    def _connected_message_default(self):
        return TimestampedMessage("", 0)

    def _chip_inserted_message_default(self):
        return TimestampedMessage("", 0)

    def traits_init(self):
        logger.info(f"Starting {self.name} listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.name,
            class_method=self.listener_actor_routine)

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    ###########################################################################
    # Publisher methods
    ###########################################################################

    def request_retry_connection(self):
        logger.info("Retrying connection...")
        publish_message("Retry connection button triggered", RETRY_CONNECTION)

        if self.no_power:
            self.no_power = False
            self.dialog_signals.close_no_power_dialog.emit()

    ###########################################################################
    # Subscriber / handler methods (_on_*_triggered)
    ###########################################################################

    @timestamped_value('connected_message')
    def _on_connected_triggered(self, body):
        logger.debug("Connected to dropbot")
        self.model.connected = True

    @timestamped_value('connected_message')
    def _on_disconnected_triggered(self, body):
        logger.debug("Disconnected from dropbot")
        self.model.connected = False
        # Force realtime mode off on disconnect
        self._on_realtime_mode_updated_triggered(TimestampedMessage("False", None), force_update=True)

    @timestamped_value('realtime_mode_message')
    def _on_realtime_mode_updated_triggered(self, body):
        realtime = body == 'True'
        logger.debug(f"Realtime mode updated to {realtime}")
        self.model.realtime_mode = realtime

    @timestamped_value('chip_inserted_message')
    def _on_chip_inserted_triggered(self, body):
        if body == 'True':
            chip_inserted = True
        elif body == 'False':
            chip_inserted = False
        else:
            logger.error(f"Invalid chip inserted value: {body}")
            chip_inserted = False
        logger.debug(f"Chip inserted: {chip_inserted}")
        self.model.chip_inserted = chip_inserted

    def _on_capacitance_updated_triggered(self, body):
        if self.model.realtime_mode:
            new_capacitance = json.loads(body).get('capacitance', '-')
            new_voltage = json.loads(body).get('voltage', '-')

            old_capacitance = self.model.capacitance
            old_voltage = self.model.voltage_readback

            self.capacitances.append(get_ureg_magnitude(new_capacitance))

            if len(self.capacitances) == NUM_CAPACITANCE_READINGS_AVERAGED:
                new_capacitance = sum(self.capacitances) / len(self.capacitances)
                new_capacitance = new_capacitance * ureg.picofarad
                new_capacitance = f"{new_capacitance:.4g~P}"
                self.capacitances = []
            else:
                new_capacitance = old_capacitance

            cap_change_significant = check_change_significance(
                old_capacitance, new_capacitance, threshold=3, threshold_type='absolute_diff')
            voltage_change_significant = check_change_significance(
                old_voltage, new_voltage, threshold=1, threshold_type='absolute_diff')

            if cap_change_significant:
                self.model.capacitance = new_capacitance

            if voltage_change_significant:
                self.model.voltage_readback = new_voltage
                force = None

                if self.model.pressure != "-":
                    force = ForceCalculationService.calculate_force_for_step(
                        get_ureg_magnitude(new_voltage),
                        get_ureg_magnitude(self.model.pressure)
                    )

                self.model.force = f"{force:.4f} mN/m" if force is not None else "-"

    def _on_calibration_data_triggered(self, body_str):
        data = json.loads(body_str)

        filler_cap = data.get('filler_capacitance_over_area')
        liquid_cap = data.get('liquid_capacitance_over_area')

        if filler_cap is not None and liquid_cap is not None:
            self.pressure_value = liquid_cap - filler_cap
            self.model.pressure = f"{self.pressure_value:.4f} pF/mm^2"

            if self.model.voltage_readback != "-":
                force = ForceCalculationService.calculate_force_for_step(
                    get_ureg_magnitude(self.model.voltage_readback),
                    self.pressure_value
                )
                self.model.force = f"{force:.4f} mN/m"
            else:
                logger.error("Voltage is not set! Cannot find Force. Recalibrate once voltage is set.")
                self.model.force = "-"
        else:
            self.model.pressure = "-"
            self.model.force = "-"

    def _on_shorts_detected_triggered(self, shorts_dict):
        shorts = json.loads(shorts_dict).get('Shorts_detected', [])
        show_window = json.loads(shorts_dict).get('Show_window', False)

        if len(shorts) == 0 and not show_window:
            logger.info("No shorts were detected.")
            return

        if len(shorts) == 0:
            title = "No shorts were detected."
            text = "No shorts were detected on any channels."
        else:
            title = "Shorts Detected"
            shorts_str = str(shorts).strip('[]')
            text = (f"Shorts were detected on the following channels: \n \n"
                    f"[{shorts_str}] \n \n"
                    f"You may continue using the DropBot, but the affected channels have "
                    f"been disabled until the DropBot is restarted (e.g. unplug all cabled and plug "
                    f"back in).")

        self.dialog_signals.show_shorts_popup.emit({'title': title, 'text': text})

    def _on_no_power_triggered(self, body):
        if self.no_power:
            return
        self.no_power = True
        self.dialog_signals.show_no_power_dialog.emit()

    def _on_halted_triggered(self, message_str):
        message_dict = json.loads(message_str)

        reason = message_dict.get('reason')
        message = message_dict.get('message')

        text = (f"DropBot has halted {reason}.\n\n"
                f"{message}")

        self.dialog_signals.show_halted_popup.emit(text)

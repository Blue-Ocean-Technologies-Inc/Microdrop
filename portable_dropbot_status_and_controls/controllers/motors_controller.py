import json

from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    FILTER_POSITIONS,
    HOME_ALL,
    LOCK_CHIP,
    MOTOR_HOME,
    MOTOR_MOVE,
    MOTOR_SET_SPEED,
    MOVE_MAGNET,
    MOVE_TRAY,
    SET_FILTER,
)

from ..consts import MM_TO_FIRMWARE_UNITS, MOTOR_MACRO_LABELS

logger = get_logger(__name__)


class MotorsController(Controller):
    """Buttons -> request topics, nothing else: the hardware picture
    lives in the status pane's mechanisms readout, never in this
    panel's own optimism. The macro buttons relabel per selected
    motor (MOTOR_MACRO_LABELS) and publish that motor's actions."""

    @observe("model:selected_motor")
    def _update_macro_labels(self, event):
        (self.model.macro_button_1_label,
         self.model.macro_button_2_label) = \
            MOTOR_MACRO_LABELS[self.model.selected_motor]

    # ------------------------------------------------------------------ #
    # Macros                                                               #
    # ------------------------------------------------------------------ #
    @observe("model:macro_button_1")
    def _macro_1(self, event):
        motor = self.model.selected_motor
        if motor == "tray":
            publish_message(topic=MOVE_TRAY, message="in")
        elif motor == "magnet":
            publish_message(topic=MOVE_MAGNET, message="engage")
        elif motor == "filter":
            self._cycle_filter(-1)
        elif motor in ("pogo_left", "pogo_right"):
            publish_message(topic=LOCK_CHIP, message="True")

    @observe("model:macro_button_2")
    def _macro_2(self, event):
        motor = self.model.selected_motor
        if motor == "tray":
            publish_message(topic=MOVE_TRAY, message="out")
        elif motor == "magnet":
            publish_message(topic=MOVE_MAGNET, message="disengage")
        elif motor == "filter":
            self._cycle_filter(+1)
        elif motor in ("pogo_left", "pogo_right"):
            publish_message(topic=LOCK_CHIP, message="False")

    def _cycle_filter(self, step):
        self.model.filter_cycle_index = \
            (self.model.filter_cycle_index + step) % len(FILTER_POSITIONS)
        publish_message(
            topic=SET_FILTER,
            message=str(FILTER_POSITIONS[self.model.filter_cycle_index]))

    @observe("model:home_button")
    def _home(self, event):
        if self.model.selected_motor == "filter":
            self.model.filter_cycle_index = 0
        logger.info(f"Homing {self.model.selected_motor}...")
        publish_message(topic=MOTOR_HOME,
                        message=self.model.selected_motor)

    @observe("model:home_all_button")
    def _home_all(self, event):
        # The coordinated resets, which also initialize the motion
        # coordinator the mechanism macros depend on after a
        # motor-board power-up.
        self.model.filter_cycle_index = 0
        logger.info("Homing all mechanisms (coordinated resets)...")
        publish_message(topic=HOME_ALL, message="True")

    # ------------------------------------------------------------------ #
    # Manual Move                                                          #
    # ------------------------------------------------------------------ #
    @observe("model:move_by_button")
    def _move_by(self, event):
        publish_message(topic=MOTOR_MOVE, message=json.dumps({
            "motor": self.model.selected_motor,
            "mode": "relative",
            "value": int(round(self.model.move_by_mm
                               * MM_TO_FIRMWARE_UNITS)),
        }))

    @observe("model:move_to_button")
    def _move_to(self, event):
        publish_message(topic=MOTOR_MOVE, message=json.dumps({
            "motor": self.model.selected_motor,
            "mode": "absolute",
            "value": int(round(self.model.move_to_mm
                               * MM_TO_FIRMWARE_UNITS)),
        }))

    @observe("model:set_speed_button")
    def _set_speed(self, event):
        publish_message(topic=MOTOR_SET_SPEED, message=json.dumps({
            "motor": self.model.selected_motor,
            "value": int(self.model.speed_um_per_s),
        }))

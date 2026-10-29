# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json

# Enthought library imports.
from traits.api import observe
from traitsui.api import Controller

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    FILTER_POSITIONS,
    HOME_ALL,
    LOCK_CHIP,
    MOTOR_HOME,
    MOTOR_MOVE,
    MOTOR_SET_SPEED,
    MOVE_MAGNET,
    SET_FILTER,
    move_tray_publisher,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import MM_TO_FIRMWARE_UNITS, MOTOR_MACRO_LABELS

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class MotorsController(Controller):
    """Buttons -> request topics, nothing else: the hardware picture
    lives in the status pane's mechanisms readout, never in this
    panel's own optimism. The macro buttons relabel per selected
    motor (MOTOR_MACRO_LABELS) and publish that motor's actions."""

    @observe("model:selected_motor")
    def _update_macro_labels(self, event):
        (self.model.macro_button_1_label, self.model.macro_button_2_label) = (
            MOTOR_MACRO_LABELS[self.model.selected_motor]
        )

    # ------------------------------------------------------------------ #
    # Macros                                                               #
    # ------------------------------------------------------------------ #
    @observe("model:macro_button_1")
    def _macro_1(self, event):
        motor = self.model.selected_motor

        if motor == "tray":
            self._move_tray("in")
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
            self._move_tray("out")
        elif motor == "magnet":
            publish_message(topic=MOVE_MAGNET, message="disengage")
        elif motor == "filter":
            self._cycle_filter(+1)
        elif motor in ("pogo_left", "pogo_right"):
            publish_message(topic=LOCK_CHIP, message="False")

    def _move_tray(self, direction):
        move_tray_publisher.publish(
            {"direction": direction, "actuate_pogos": not self.model.tray_only}
        )

    def _cycle_filter(self, step):
        self.model.filter_cycle_index = (self.model.filter_cycle_index + step) % len(
            FILTER_POSITIONS
        )
        publish_message(
            topic=SET_FILTER,
            message=str(FILTER_POSITIONS[self.model.filter_cycle_index]),
        )

    @observe("model:home_button")
    def _home(self, event):
        if self.model.selected_motor == "filter":
            self.model.filter_cycle_index = 0

        logger.info(f"Homing {self.model.selected_motor}...")
        publish_message(topic=MOTOR_HOME, message=self.model.selected_motor)

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
        publish_message(
            topic=MOTOR_MOVE,
            message=json.dumps(
                {
                    "motor": self.model.selected_motor,
                    "mode": "relative",
                    "value": int(round(self.model.move_by_mm * MM_TO_FIRMWARE_UNITS)),
                }
            ),
        )

    @observe("model:move_to_button")
    def _move_to(self, event):
        publish_message(
            topic=MOTOR_MOVE,
            message=json.dumps(
                {
                    "motor": self.model.selected_motor,
                    "mode": "absolute",
                    "value": int(round(self.model.move_to_mm * MM_TO_FIRMWARE_UNITS)),
                }
            ),
        )

    @observe("model:set_speed_button")
    def _set_speed(self, event):
        publish_message(
            topic=MOTOR_SET_SPEED,
            message=json.dumps(
                {
                    "motor": self.model.selected_motor,
                    "value": int(self.model.speed_um_per_s),
                }
            ),
        )

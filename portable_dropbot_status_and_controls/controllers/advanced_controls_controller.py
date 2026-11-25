# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.api import GUI, YES
from traits.api import observe
from traitsui.api import Controller

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import confirm
from portable_dropbot_controller.consts import (
    MOTOR_PARAMS_PRESET,
    MOTOR_PARAMS_READ,
    REBOOT_MOTOR_BOARD,
    SET_BUZZER,
    motor_params_write_publisher,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The vendor's MOTOR_HOME_PAIR_FIELDS / MOTOR_HOME_PAIR_WARNING, paraphrased
#: for a frontend running without the driver package.
HOME_PAIR_FIELDS_FALLBACK = ("motor_polarity", "home_dir")
HOME_PAIR_WARNING_FALLBACK = (
    "Home direction and polarity change together or homing runs away; "
    "changing home direction un-homes the axis (re-home it after the write)."
)
#: Motor firmware 1.0.0.28, which the vendor's 1.8.0 pairing text predates.
HOME_PAIR_MOTOR_28_NOTE = (
    "On motor firmware 1.0.0.28 and later a polarity change un-homes the axis "
    "too, and the board refuses either change while the axis moves."
)


class AdvancedControlsController(Controller):
    """Toggles and buttons -> request topics. Flash persistence, the
    reboot and a home direction / polarity edit are behind confirms —
    each outlives the session or can send homing the wrong way."""

    # ------------------------------------------------------------------ #
    # Power system                                                          #
    # ------------------------------------------------------------------ #
    @observe("model:buzzer_state")
    def _buzzer_state_change(self, event):
        publish_message(topic=SET_BUZZER, message=str(event.new))
        logger.debug(
            f"Buzzer state change to {event.new} requested: published to {SET_BUZZER}"
        )

    # ------------------------------------------------------------------ #
    # Motor params                                                          #
    # ------------------------------------------------------------------ #
    @observe("model:selected_motor")
    def _on_motor_changed(self, event):
        # The fields on screen belong to the previous motor now:
        # require a fresh read before they can be written anywhere.
        self.model.params_loaded = False
        self.model.loaded_fields = []
        self.model.board_values = {}
        self.model.params_layout = "-"
        self.model.params_status = "-"

        if self.model.connected:
            publish_message(topic=MOTOR_PARAMS_READ, message=self.model.selected_motor)

    @observe("model:read_button")
    def _read(self, event):
        publish_message(topic=MOTOR_PARAMS_READ, message=self.model.selected_motor)

    @observe("model:write_button")
    def _write(self, event):
        motor_params_write_publisher.publish(
            {
                "motor": self.model.selected_motor,
                "fields": {
                    name: getattr(self.model, name) for name in self.model.loaded_fields
                },
            }
        )
        logger.info(
            f"Requested {self.model.selected_motor} params write "
            f"({len(self.model.loaded_fields)} fields)"
        )

    @observe("model:[motor_polarity,home_dir]")
    def _confirm_home_pair(self, event):
        """Home direction and polarity are one setting (the vendor's pairing
        warning): an edit of either asks first, and No puts back the
        board's value."""
        baseline = self.model.board_values.get(event.name)

        if not self.model.params_loaded or baseline is None or event.new == baseline:
            return

        # The frontend may run without the driver package; only this
        # confirm needs the vendor's own pairing text, and without it the
        # confirm still runs on a paraphrase — the edit is never let through
        # unasked.
        try:
            from dropbot_portable.param_layout import (
                MOTOR_HOME_PAIR_FIELDS,
                MOTOR_HOME_PAIR_WARNING,
            )
        except ImportError:
            logger.warning("dropbot_portable missing: home pair warning paraphrased")
            MOTOR_HOME_PAIR_FIELDS = HOME_PAIR_FIELDS_FALLBACK
            MOTOR_HOME_PAIR_WARNING = HOME_PAIR_WARNING_FALLBACK

        other = next(name for name in MOTOR_HOME_PAIR_FIELDS if name != event.name)
        answer = confirm(
            None,
            f"{self.model.selected_motor} {event.name}: {baseline} → {event.new}."
            f"\n\n{MOTOR_HOME_PAIR_WARNING}\n\n{HOME_PAIR_MOTOR_28_NOTE}"
            f"\n\nCheck {other} before Write. "
            f"Keep this edit?",
            title="Home direction and polarity",
        )

        # Deferred: the text editor that made this edit ignores a value set
        # while it is still committing it, so a direct revert leaves the old
        # text on screen.
        if answer != YES:
            GUI.invoke_later(setattr, self.model, event.name, baseline)

    @observe("model:preset_button")
    def _preset(self, event):
        motor = self.model.selected_motor
        answer = confirm(
            None,
            f"Persist the {motor} motor's CURRENT on-device params "
            f"to flash (survives reboot)? Write first if you have "
            f"unsaved edits.",
            title="Preset to Flash",
        )

        if answer != YES:
            return

        publish_message(topic=MOTOR_PARAMS_PRESET, message=motor)

    @observe("model:reboot_button")
    def _reboot(self, event):
        answer = confirm(
            None,
            "Soft-reset the motor board? Params already apply live on a "
            "write, so this is only needed for boot-only settings. The "
            "board re-runs its boot homing afterwards (all axes move, "
            "~30 s); motor commands answer busy until it finishes.",
            title="Reboot Motor Board",
        )

        if answer != YES:
            return

        self.model.params_status = "rebooting motor board..."
        publish_message(topic=REBOOT_MOTOR_BOARD, message="")

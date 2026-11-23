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

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from pyface.api import YES
from traits.api import observe
from traitsui.api import Controller

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import confirm
from portable_dropbot_controller.consts import (
    HEATER_TUNE_CANCEL,
    PMT_POWER,
    PMT_SET_GAIN,
    TEMP_CONTROL,
    TEMP_READ_INFO,
    TEMP_READ_PID,
    TEMP_SET_TARGET,
    TempSetPidRequest,
    heater_tune_apply_publisher,
    heater_tune_start_publisher,
    temp_set_pid_publisher,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class MoreControlsController(Controller):
    """Toggles and buttons -> request topics. The PMT's actual power
    state comes back through the message handler on PMT_UPDATED. Heater
    auto-tune proposals are written only after a confirm."""

    # ------------------------------------------------------------------ #
    # Temperature control                                                  #
    # ------------------------------------------------------------------ #
    @observe("model:set_target_button")
    def _set_target(self, event):
        publish_message(
            topic=TEMP_SET_TARGET,
            message=json.dumps(
                {
                    "channel": int(self.model.temp_channel),
                    "target_c": float(self.model.temp_target_c),
                }
            ),
        )

    @observe("model:temp_control_on")
    def _on_temp_control_changed(self, event):
        publish_message(
            topic=TEMP_CONTROL,
            message=json.dumps(
                {
                    "channel": int(self.model.temp_channel),
                    "on": bool(event.new),
                }
            ),
        )
        logger.info(
            f"Temp control ch{self.model.temp_channel} --> "
            f"{'on' if event.new else 'off'}"
        )

    @observe("model:read_info_button")
    def _read_info(self, event):
        publish_message(topic=TEMP_READ_INFO, message=str(int(self.model.temp_channel)))

    @observe("model:temp_channel")
    def _on_temp_channel_changed(self, event):
        # The PID fields on screen belong to the previous channel now.
        self.model.pid_status = "-"

        if self.model.connected:
            self._read_pid(event)

    @observe("model:read_pid_button")
    def _read_pid(self, event):
        publish_message(topic=TEMP_READ_PID, message=str(int(self.model.temp_channel)))

    @observe("model:apply_pid_button")
    def _apply_pid(self, event):
        try:
            request = TempSetPidRequest(
                channel=self.model.temp_channel,
                kp=self.model.pid_kp,
                ki=self.model.pid_ki,
                kd=self.model.pid_kd,
                period_ms=self.model.pid_period_ms,
            )
        except ValidationError as error:
            self.model.pid_status = f"Not applied: {error.errors()[0]['msg']}"
            return

        self.model.pid_status = "Applying..."
        temp_set_pid_publisher.publish(request.model_dump())

    # ------------------------------------------------------------------ #
    # Heater auto-tune                                                     #
    # ------------------------------------------------------------------ #
    @observe("model:heater_tune:start_button")
    def _start_heater_tune(self, event):
        tune = self.model.heater_tune
        tune.status = "Starting..."

        heater_tune_start_publisher.publish(
            {
                "channel": int(self.model.temp_channel),
                "duty_pct": tune.duty_pct,
                "max_temp_c": tune.max_temp_c,
                "max_duration_s": tune.max_duration_s,
            }
        )

    @observe("model:heater_tune:cancel_button")
    def _cancel_heater_tune(self, event):
        publish_message(topic=HEATER_TUNE_CANCEL, message="")

    @observe("model:heater_tune:apply_button")
    def _apply_heater_tune(self, event):
        """Write the selected style's proposal to the fitted channel once the
        operator confirms; the backend re-checks it against the firmware."""
        tune = self.model.heater_tune
        proposal = tune.proposals.get(tune.style)

        if proposal is None or not tune.smith_model:
            return

        lasting = (
            "They are saved to flash and survive a reboot."
            if tune.persist
            else "They last until the next reboot."
        )
        answer = confirm(
            None,
            f"Write to heater ch{tune.result_channel}: {tune.proposal_display}?"
            f"\n\nWriting the model re-initialises both heater loops. {lasting}",
            title="Apply Heater Tuning",
        )

        if answer != YES:
            return

        tune.status = "Applying..."
        heater_tune_apply_publisher.publish(
            {
                "channel": tune.result_channel,
                "kp": proposal["kp"],
                "ki": proposal["ki"],
                "kd": proposal["kd"],
                "smith_model": tuple(tune.smith_model),
                "persist": tune.persist,
            }
        )

    # ------------------------------------------------------------------ #
    # PMT                                                                  #
    # ------------------------------------------------------------------ #
    @observe("model:pmt_power")
    def _on_pmt_power_changed(self, event):
        publish_message(topic=PMT_POWER, message=str(bool(event.new)))
        logger.info(f"PMT power --> {'on' if event.new else 'off'}")

    @observe("model:set_gain_button")
    def _set_gain(self, event):
        publish_message(topic=PMT_SET_GAIN, message=str(int(self.model.pmt_gain)))

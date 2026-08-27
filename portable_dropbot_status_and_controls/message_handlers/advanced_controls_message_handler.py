# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import json

from traits.api import Instance

from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

from ..models.advanced_controls_model import (
    PortableDropbotAdvancedControlsModel,
)


class PortableDropbotAdvancedControlsMessageHandler(BaseMessageHandler):
    """Connection greying (inherited), the Advanced Mode toggle that
    unlocks the pane, and the MOTOR_PARAMS_UPDATED stream: read-back
    field values and write/preset/reboot outcomes."""

    model = Instance(PortableDropbotAdvancedControlsModel)

    def _on_advanced_mode_change_triggered(self, body):
        self.model.advanced_mode = str(body).lower() == "true"

    def _on_motor_params_updated_triggered(self, body):
        data = json.loads(str(body))
        if "motor_board_rebooted" in data:
            self.model.params_status = (
                "Motor board rebooted — Home All from the motor panel"
                if data["motor_board_rebooted"]
                else "Motor board reboot FAILED — see log")
            return
        motor = data.get("motor")
        if "error" in data:
            self.model.params_status = f"{motor}: {data['error']}"
            return
        if "written" in data:
            self.model.params_status = (
                f"{motor}: written to RAM" if data["written"]
                else f"{motor}: write FAILED — see log")
            return
        if "preset" in data:
            self.model.params_status = (
                f"{motor}: persisted to flash — reboot to take effect"
                if data["preset"]
                else f"{motor}: preset FAILED — see log")
            return
        if "fields" in data:
            # A read for a motor no longer selected is stale: showing
            # its values under the current selection would invite a
            # cross-motor write.
            if motor != self.model.selected_motor:
                return
            fields = data["fields"]
            for name, value in fields.items():
                setattr(self.model, name, value)
            self.model.loaded_fields = list(fields)
            self.model.params_loaded = True
            self.model.params_status = \
                f"{motor}: read {len(fields)} fields"

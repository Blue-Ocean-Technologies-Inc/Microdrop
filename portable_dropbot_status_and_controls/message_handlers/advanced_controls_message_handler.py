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
from traits.api import Instance

# Microdrop package imports.
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

# Local imports.
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
        motor = data.get("motor")

        if "motor_board_rebooted" in data:
            self.model.params_status = (
                "Motor board rebooted — boot homing runs (~30 s); motor "
                "commands answer busy until it finishes"
                if data["motor_board_rebooted"]
                else "Motor board reboot FAILED — see log"
            )
        elif "error" in data:
            self.model.params_status = f"{motor}: {data['error']}"
        elif "written" in data:
            self._adopt_write(motor, data["written"])
        elif "preset" in data:
            self.model.params_status = (
                f"{motor}: persisted to flash"
                if data["preset"]
                else f"{motor}: preset FAILED — see log"
            )
        elif "fields" in data and motor == self.model.selected_motor:
            # A read for a motor no longer selected is stale: showing its
            # values under the current selection would invite a cross-motor
            # write.
            self._adopt_read(motor, data)

    def _adopt_read(self, motor, data):
        fields = data["fields"]

        # Unloaded while the values land, so the home direction / polarity
        # pairing confirm takes them for the board's, not for edits.
        self.model.params_loaded = False

        for name, value in fields.items():
            setattr(self.model, name, value)

        self.model.board_values = dict(fields)
        self.model.loaded_fields = list(fields)
        self.model.params_layout = (
            f"{data['blob_size']} B blob, speeds shown in real µm/s "
            f"(board: {data['speed_units']})"
        )
        self.model.params_loaded = True
        self.model.params_status = f"{motor}: read {len(fields)} fields"

    def _adopt_write(self, motor, written):
        """An accepted write becomes the new board baseline; a changed home
        direction has un-homed the axis on the board."""
        if not written:
            self.model.params_status = f"{motor}: write FAILED — see log"
            return

        values = {name: getattr(self.model, name) for name in self.model.loaded_fields}
        rehome = values.get("home_dir") != self.model.board_values.get("home_dir")

        self.model.board_values = values
        self.model.params_status = (
            f"{motor}: written to RAM, live — the home direction changed, so "
            f"the axis is UN-HOMED: re-home it before moving"
            if rehome
            else f"{motor}: written to RAM, live (Preset to keep it)"
        )

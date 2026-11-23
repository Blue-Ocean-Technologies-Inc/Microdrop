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
from portable_dropbot_controller.consts import (
    TEMP_PID_GAIN_BOUNDS,
    TEMP_READ_PID,
    HeaterTuneApplied,
    HeaterTuneDone,
    HeaterTuneProgress,
)
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

# Microdrop utils imports.
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..models.more_controls_model import PortableDropbotMoreControlsModel


class PortableDropbotMoreControlsMessageHandler(BaseMessageHandler):
    """Connection greying (inherited), the TEMP_UPDATED stream
    (per-channel readings and PID readbacks), the heater auto-tune
    feedback, and the PMT_UPDATED stream (actual power state)."""

    model = Instance(PortableDropbotMoreControlsModel)

    @timestamped_value("connected_message")
    def _on_connected_triggered(self, body):
        self.model.connected = True
        # Fill the PID fields from the board: Apply needs them.
        publish_message(topic=TEMP_READ_PID, message=str(self.model.temp_channel))

    def _on_temp_updated_triggered(self, body):
        data = json.loads(str(body))
        channel = data.get("channel")
        # PID readbacks and outcomes belong to the selected channel only.
        selected = channel == self.model.temp_channel

        if "pid" in data and selected:
            self._adopt_pid(data["pid"])
        elif "pid_applied" in data and selected:
            if data["pid_error"]:
                self.model.pid_status = f"Not applied: {data['pid_error']}"
            elif data["pid_applied"]:
                self.model.pid_status = "Applied"
            else:
                self.model.pid_status = "Apply FAILED — see log"
        elif "current_c" in data:
            self.model.temp_info_display = (
                f"ch{channel}: {data['current_c']:.2f} °C "
                f"(target {data['target_c']:.2f} °C, "
                f"output {data['output_pct']:.1f} %)"
            )

    def _adopt_pid(self, pid):
        """Show a PID readback; gains the firmware would now refuse (stored
        by older firmware) are reported instead of loaded."""
        low, high = TEMP_PID_GAIN_BOUNDS
        gains = {name: float(pid[name]) for name in ("kp", "ki", "kd")}
        outside = [
            f"{name}={value:g}"
            for name, value in gains.items()
            if not low <= value <= high
        ]

        if outside:
            self.model.pid_status = (
                f"Board holds gains outside {low:g}–{high:g} "
                f"({', '.join(outside)}): enter new ones"
            )
            return

        self.model.pid_kp = gains["kp"]
        self.model.pid_ki = gains["ki"]
        self.model.pid_kd = gains["kd"]
        self.model.pid_period_ms = int(pid["period_ms"])
        self.model.pid_status = "Read from the board"

    def _on_heater_tune_progress_triggered(self, body):
        self.model.heater_tune.adopt_progress(
            HeaterTuneProgress.model_validate_json(str(body))
        )

    def _on_heater_tune_done_triggered(self, body):
        self.model.heater_tune.adopt_done(HeaterTuneDone.model_validate_json(str(body)))

    def _on_heater_tune_applied_triggered(self, body):
        applied = HeaterTuneApplied.model_validate_json(str(body))
        self.model.heater_tune.adopt_applied(applied)

        # The PID fields show the board's gains: refresh them.
        if applied.gains and applied.channel == self.model.temp_channel:
            publish_message(topic=TEMP_READ_PID, message=str(applied.channel))

    def _on_pmt_updated_triggered(self, body):
        data = json.loads(str(body))
        if "power" in data:
            self.model.pmt_power = bool(data["power"])

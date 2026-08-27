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

from ..models.more_controls_model import PortableDropbotMoreControlsModel


class PortableDropbotMoreControlsMessageHandler(BaseMessageHandler):
    """Connection greying (inherited), the TEMP_UPDATED stream
    (per-channel readings and PID readbacks), and the PMT_UPDATED
    stream (actual power state and acquire outcomes)."""

    model = Instance(PortableDropbotMoreControlsModel)

    def _on_temp_updated_triggered(self, body):
        data = json.loads(str(body))
        channel = data.get("channel")
        if "pid" in data:
            if channel == self.model.temp_channel:
                pid = data["pid"]
                self.model.pid_kp = float(pid["kp"])
                self.model.pid_ki = float(pid["ki"])
                self.model.pid_kd = float(pid["kd"])
                self.model.pid_period_ms = int(pid["period_ms"])
            return
        if "current_c" in data:
            self.model.temp_info_display = (
                f"ch{channel}: {data['current_c']:.2f} °C "
                f"(target {data['target_c']:.2f} °C, "
                f"output {data['output_pct']:.1f} %)")

    def _on_pmt_updated_triggered(self, body):
        data = json.loads(str(body))
        if "power" in data:
            self.model.pmt_power = bool(data["power"])
        if "acquiring" in data:
            self.model.acquiring = bool(data["acquiring"])
        if "acquired_packets" in data:
            packets = data["acquired_packets"]
            self.model.pmt_status_display = (
                f"Acquired {packets} packets" if packets is not None
                else "Acquire FAILED — see log")

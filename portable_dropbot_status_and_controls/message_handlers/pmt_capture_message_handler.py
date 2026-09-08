# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Connection greying (inherited) plus the PMT Capture pane's three
signals: the spot table, per-stage progress, and the capture outcome."""

# Enthought library imports.
from traits.api import Instance

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    PMT_SPOTS_READ,
    PmtCaptureDone,
    PmtCaptureProgress,
    PmtSpotsUpdated,
)
from template_status_and_controls.base_message_handler import (
    BaseMessageHandler,
)

# Microdrop utils imports.
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..models.pmt_capture_model import PortableDropbotPmtCaptureModel


class PortableDropbotPmtCaptureMessageHandler(BaseMessageHandler):
    model = Instance(PortableDropbotPmtCaptureModel)

    @timestamped_value("connected_message")
    def _on_connected_triggered(self, body):
        self.model.connected = True
        # Pull the board's spot table so the rows show reality.
        publish_message(topic=PMT_SPOTS_READ, message="")

    def _on_pmt_spots_updated_triggered(self, body):
        data = PmtSpotsUpdated.model_validate_json(str(body))
        self.model.merge_spots((s.slot, s.position_um) for s in data.spots)

    def _on_pmt_capture_progress_triggered(self, body):
        p = PmtCaptureProgress.model_validate_json(str(body))
        self.model.capturing = True
        self.model.progress = (
            f"Spot {p.slot} ({p.index + 1}/{p.total}): {p.stage} {p.detail}".rstrip()
        )

    def _on_pmt_capture_done_triggered(self, body):
        done = PmtCaptureDone.model_validate_json(str(body))
        self.model.capturing = False
        self.model.results_directory = done.directory
        saved = sum(1 for r in done.results if r.csv_path)
        failed = [r for r in done.results if r.error]
        if done.error:
            self.model.progress = f"FAILED: {done.error}"
        elif done.aborted:
            self.model.progress = f"Aborted after {saved} spot(s)"
        elif done.ok:
            self.model.progress = f"{saved}/{len(done.results)} spots saved"
        else:
            self.model.progress = f"FAILED: spot {failed[0].slot} — {failed[0].error}"

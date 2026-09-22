# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Connection greying and "pane follows step" (both inherited — see
capture_pane_message_handler.py) plus the Fluorescence Capture pane's
capture progress and outcome."""

# Enthought library imports.
from traits.api import Instance

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    FluorescenceCaptureDone,
    FluorescenceCaptureProgress,
)
from portable_dropbot_protocol_controls.consts import FLUORESCENCE_CAPTURE_COLUMN_ID

# Local imports.
from ..models.fluorescence_capture_model import PortableDropbotFluorescenceCaptureModel
from .capture_pane_message_handler import CapturePaneMessageHandler


class PortableDropbotFluorescenceCaptureMessageHandler(CapturePaneMessageHandler):
    STEP_COLUMN_ID = FLUORESCENCE_CAPTURE_COLUMN_ID

    model = Instance(PortableDropbotFluorescenceCaptureModel)

    def _on_fluorescence_capture_progress_triggered(self, body):
        p = FluorescenceCaptureProgress.model_validate_json(str(body))

        self.capture_progressed(
            p.filter_position,
            f"Filter {p.filter_position} ({p.index + 1}/{p.total}): "
            f"{p.stage} {p.detail}".rstrip(),
        )

    def _on_fluorescence_capture_done_triggered(self, body):
        done = FluorescenceCaptureDone.model_validate_json(str(body))

        self.capture_finished(done)

        if done.error:
            self.model.progress = f"FAILED: {done.error}"
        elif done.ok:
            self.model.progress = f"{len(done.frames)} frame(s) saved"
        else:
            self.model.progress = "FAILED: aborted"

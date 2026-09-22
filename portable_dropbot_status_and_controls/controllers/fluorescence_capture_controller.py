# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> request topics for the Fluorescence Capture pane — all of it
shared with every capture pane (see capture_pane_controller.py) but the
request itself. Progress and outcomes come back through the message
handler."""

# Standard library imports.
import uuid

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    FLUORESCENCE_CAPTURE_ABORT,
    fluorescence_capture_publisher,
)
from portable_dropbot_protocol_controls.consts import FLUORESCENCE_CAPTURE_COLUMN_ID

# Local imports.
from .capture_pane_controller import CapturePaneController


class FluorescenceCaptureController(CapturePaneController):
    STEP_COLUMN_ID = FLUORESCENCE_CAPTURE_COLUMN_ID
    ABORT_TOPIC = FLUORESCENCE_CAPTURE_ABORT
    ROW_NOUN = "filter"

    def _publish_capture_request(self):
        request = self.model.capture_request(
            request_id=str(uuid.uuid4()), label="manual"
        )

        fluorescence_capture_publisher.publish(request)

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> request topics for the PMT Capture pane; spots, progress and
the outcome come back through the message handler."""

# Enthought library imports.
from traits.api import observe
from traitsui.api import Controller

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    PMT_CAPTURE_ABORT,
    PMT_SPOTS_READ,
    pmt_capture_publisher,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PmtCaptureController(Controller):
    @observe("model:start_button")
    def _start_capture(self, event):
        entries = self.model.capture_entries()
        if not entries:
            self.model.progress = "No spot ticked"
            return
        self.model.capturing = True
        self.model.progress = "starting..."
        logger.info(f"Requested PMT capture of {len(entries)} spot(s)")
        pmt_capture_publisher.publish({"entries": entries})

    @observe("model:abort_button")
    def _abort_capture(self, event):
        publish_message(topic=PMT_CAPTURE_ABORT, message="")

    @observe("model:refresh_button")
    def _refresh_spots(self, event):
        publish_message(topic=PMT_SPOTS_READ, message="")

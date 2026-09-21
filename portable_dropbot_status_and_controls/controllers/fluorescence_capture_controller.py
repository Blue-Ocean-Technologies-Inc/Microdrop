# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> request topics for the Fluorescence Capture pane. Progress and
outcomes come back through the message handler.

"Pane follows step" (mirrors #601 increment 2 for PMT): while a step is
attached and no protocol is running, every row edit publishes the step's
fluorescence_capture cell over protocol_tree_set_cell_publisher — the
model's loading_step flag suppresses this while attach_step/detach_step are
themselves applying a loaded cell or the manual snapshot."""

# Standard library imports.
import uuid

# Enthought library imports.
from traits.api import observe
from traitsui.api import Controller

# Microdrop package imports.
from pluggable_protocol_tree.consts import protocol_tree_set_cell_publisher
from portable_dropbot_controller.consts import (
    FLUORESCENCE_CAPTURE_ABORT,
    fluorescence_capture_publisher,
)
from portable_dropbot_protocol_controls.consts import FLUORESCENCE_CAPTURE_COLUMN_ID

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.file_handler import open_file

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class FluorescenceCaptureController(Controller):
    # ------------------------------------------------------------------ #
    # Capture                                                               #
    # ------------------------------------------------------------------ #

    @observe("model:start_button")
    def _start_capture(self, event):
        entries = self.model.capture_entries()

        if not entries:
            self.model.status = "No filter ticked"
            return

        self.model.running = True
        self.model.status = "starting..."
        request_id = str(uuid.uuid4())
        logger.info(f"Requested fluorescence capture of {len(entries)} filter(s)")
        fluorescence_capture_publisher.publish(
            self.model.capture_request(request_id=request_id, label="manual")
        )

    @observe("model:abort_button")
    def _abort_capture(self, event):
        publish_message(topic=FLUORESCENCE_CAPTURE_ABORT, message="")

    # ------------------------------------------------------------------ #
    # Pane follows step                                                     #
    # ------------------------------------------------------------------ #

    @observe("model:rows:items:led_percent")
    @observe("model:rows:items:exposure_ms")
    @observe("model:rows:items:auto_focus")
    @observe("model:rows:items:focus_distance")
    @observe("model:rows:items:at_start")
    @observe("model:rows:items:at_end")
    @observe("model:rows:items")
    @observe("model:rows")
    def _push_attached_step(self, event):
        # Not attached, mid-run (the tree refuses set-cell then anyway), or
        # attach_step/detach_step applying a loaded cell or the manual
        # snapshot — none of those are an operator edit to push.
        if (
            not self.model.attached_step_id
            or self.model.protocol_running
            or self.model.loading_step
        ):
            return

        value = self.model.step_cell_value()
        self.model.record_pushed_value(value)
        protocol_tree_set_cell_publisher.publish(
            step_id=self.model.attached_step_id,
            col_id=FLUORESCENCE_CAPTURE_COLUMN_ID,
            value=value,
        )

    # ------------------------------------------------------------------ #
    # Results                                                              #
    # ------------------------------------------------------------------ #

    @observe("model:result_rows:items:open_file")
    def _open_result_file(self, event):
        path = event.object.path

        try:
            open_file(path)
        except OSError as error:
            logger.error(f"Could not open fluorescence capture file {path}: {error}")

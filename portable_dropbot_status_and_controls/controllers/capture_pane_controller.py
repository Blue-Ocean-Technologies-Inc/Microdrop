# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Buttons -> request topics shared by the capture panes (see
capture_pane_model.py): start and abort a capture, page the results, open a
result file, and "pane follows step" — while a step is attached and no
protocol is running, every row edit publishes the step's cell over
protocol_tree_set_cell_publisher. The model's loading_step flag suppresses
this while attach_step/detach_step are themselves applying a loaded cell or
the manual snapshot."""

# Standard library imports.
import uuid

# Enthought library imports.
from traits.api import observe
from traitsui.api import Controller

# Microdrop package imports.
from pluggable_protocol_tree.consts import protocol_tree_set_cell_publisher

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.file_handler import open_file
from microdrop_utils.traitsui_qt_helpers import fit_table_editor_height_to_rows

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class CapturePaneController(Controller):
    """Subclasses set the class constants and publish their own request."""

    #: The protocol-tree column the attached step's cell lives in.
    STEP_COLUMN_ID = ""
    #: Topic that aborts the pane's running capture.
    ABORT_TOPIC = ""
    #: What the capture visits, for the status line ("spot", "filter").
    ROW_NOUN = ""

    def _publish_capture_request(self, request_id):
        """Publish the pane's capture request for the ticked rows, tagged
        with `request_id` so the pane can recognize its own progress/done
        later."""
        raise NotImplementedError

    def init(self, info):
        # Both row tables (manual and attached) hug their rows, so the run
        # buttons sit right under the last one.
        for editor in info.ui.get_editors("rows"):
            fit_table_editor_height_to_rows(editor)

        return super().init(info)

    # ------------------------------------------------------------------ #
    # Capture                                                               #
    # ------------------------------------------------------------------ #

    @observe("model:start_button")
    def _start_capture(self, event):
        entries = self.model.capture_entries()

        if not entries:
            self.model.progress = f"No {self.ROW_NOUN} ticked"

            return

        request_id = str(uuid.uuid4())
        self.model.capture_request_id = request_id
        self.model.capturing = True
        self.model.progress = "starting..."
        logger.info(f"Requested capture of {len(entries)} {self.ROW_NOUN}(s)")

        self._publish_capture_request(request_id)

    @observe("model:abort_button")
    def _abort_capture(self, event):
        publish_message(topic=self.ABORT_TOPIC, message="")

    # ------------------------------------------------------------------ #
    # Pane follows step                                                     #
    # ------------------------------------------------------------------ #

    @observe("model:park_motor")
    @observe("model:rows:items:+setting")
    @observe("model:rows:items:[at_start,at_end]")
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
            col_id=self.STEP_COLUMN_ID,
            value=value,
        )

    # ------------------------------------------------------------------ #
    # Results                                                              #
    # ------------------------------------------------------------------ #

    @observe("model:previous_frame_button")
    def _show_previous_frame(self, event):
        self.model.show_previous_frame()

    @observe("model:next_frame_button")
    def _show_next_frame(self, event):
        self.model.show_next_frame()

    @observe("model:result_frames:items:rows:items:open_file")
    def _open_result_file(self, event):
        path = event.object.path

        try:
            open_file(path)
        except OSError as error:
            logger.error(f"Could not open capture file {path}: {error}")

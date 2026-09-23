# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Connection greying (inherited) plus the signals every capture pane
shares (see capture_pane_model.py): the "pane follows step" attach/detach
driven by the protocol tree's row selection, and the bookkeeping around a
capture's progress and outcome. Qt-free — every handler here only mutates
model traits, safe from this actor's Dramatiq worker thread."""

# Microdrop package imports.
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeRowSelectedMessage
from template_status_and_controls.base_message_handler import BaseMessageHandler

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class CapturePaneMessageHandler(BaseMessageHandler):
    """Subclasses set STEP_COLUMN_ID and handle their own capture topics,
    reporting through capture_progressed/capture_finished."""

    #: The protocol-tree column the attached step's cell lives in.
    STEP_COLUMN_ID = ""
    #: The other capture pane's column: a step sets only one of the two.
    EXCLUSIVE_COLUMN_ID = ""

    # ------------------------------------------------------------------ #
    # Pane follows step (PROTOCOL_TREE_ROW_SELECTED's last topic segment    #
    # is "row_selected" — see basic_listener_actor_routine)                 #
    # ------------------------------------------------------------------ #

    def _on_row_selected_triggered(self, body):
        """A step selection loads its cell into the table; a group or empty
        selection returns to manual mode. A rebroadcast that carries
        exactly the value we last pushed for this step is our own set-cell
        echoing back (skip it, not a reload) — a rebroadcast carrying a
        DIFFERENT value for the same step is a genuine external change
        (reload)."""

        try:
            msg = ProtocolTreeRowSelectedMessage.deserialize(str(body))
        except Exception as error:
            logger.warning(f"Unparseable row-selected payload: {error}")

            return

        if not msg.step_id:
            self.model.detach_step()

            return

        cell_value = msg.cells.get(self.STEP_COLUMN_ID)

        # Locked only while this pane's own cell is empty — a step with both
        # (hand-edited, older) stays editable here so one can be cleared.
        self.model.step_capture_taken = bool(
            msg.cells.get(self.EXCLUSIVE_COLUMN_ID) and not cell_value
        )

        if (
            msg.step_id == self.model.last_pushed_step_id
            and cell_value == self.model.last_pushed_value
        ):
            return  # echo of our own push

        self.model.attach_step(msg.step_id, cell_value, self._step_label(msg.cells))

    @staticmethod
    def _step_label(cells):
        """'1.2 · Wash' from the tree's id (0-indexed path) and name cells;
        empty when the tree sent neither."""
        path = cells.get("id") or []
        number = ".".join(str(index + 1) for index in path)
        name = cells.get("name") or ""

        return " · ".join(part for part in (number, name) if part)

    # ------------------------------------------------------------------ #
    # Capture                                                              #
    # ------------------------------------------------------------------ #

    def _is_own_capture(self, request_id):
        """True when `request_id` names the capture this pane started and
        is still following. A protocol step mints its own request_id for
        its captures (see the *_capture_column.py handlers), so a
        progress/done from one of those — or a stale echo — is not this
        pane's to show."""
        return bool(request_id) and request_id == self.model.capture_request_id

    def capture_progressed(self, key, progress):
        """A capture moved on to the row keyed `key`: highlight it and show
        the stage on the status line."""
        self.model.capturing = True
        self.model.mark_active_row(key)
        self.model.progress = progress

    def capture_finished(self, done):
        """A capture ended: clear the highlight and stop following it, and
        — unless the request was refused (directory="" — never overwrite
        the previous run's folder and results with that) — record the
        saved-to folder and the run's results."""
        self.model.capturing = False
        self.model.mark_active_row(None)
        self.model.capture_request_id = ""

        if done.directory:
            self.model.results_directory = done.directory
            self.model.add_result_frame(done)

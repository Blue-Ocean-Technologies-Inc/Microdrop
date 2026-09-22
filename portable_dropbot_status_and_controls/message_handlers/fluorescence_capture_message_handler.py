# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Connection greying (inherited) plus the Fluorescence Capture pane's
signals: capture progress and outcome, and the "pane follows step"
attach/detach driven by the protocol tree's row selection. Qt-free — every
handler here only mutates model traits, safe from this actor's Dramatiq
worker thread."""

# Enthought library imports.
from traits.api import Instance

# Microdrop package imports.
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeRowSelectedMessage
from portable_dropbot_controller.consts import (
    FluorescenceCaptureDone,
    FluorescenceCaptureProgress,
)
from portable_dropbot_protocol_controls.consts import FLUORESCENCE_CAPTURE_COLUMN_ID
from template_status_and_controls.base_message_handler import BaseMessageHandler

# Local imports.
from ..models.fluorescence_capture_model import PortableDropbotFluorescenceCaptureModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PortableDropbotFluorescenceCaptureMessageHandler(BaseMessageHandler):
    model = Instance(PortableDropbotFluorescenceCaptureModel)

    # ------------------------------------------------------------------ #
    # Pane follows step (PROTOCOL_TREE_ROW_SELECTED's last topic segment    #
    # is "row_selected" — see basic_listener_actor_routine)                 #
    # ------------------------------------------------------------------ #

    def _on_row_selected_triggered(self, body):
        """A step selection loads its fluorescence_capture cell into the
        table; a group or empty selection returns to manual mode. A
        rebroadcast that carries exactly the value we last pushed for this
        step is our own set-cell echoing back (skip it, not a reload) — a
        rebroadcast carrying a DIFFERENT value for the same step is a
        genuine external change (reload)."""

        try:
            msg = ProtocolTreeRowSelectedMessage.deserialize(str(body))
        except Exception as error:
            logger.warning(f"Unparseable row-selected payload: {error}")

            return

        if not msg.step_id:
            self.model.detach_step()

            return

        cell_value = msg.cells.get(FLUORESCENCE_CAPTURE_COLUMN_ID)

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

    def _on_fluorescence_capture_progress_triggered(self, body):
        p = FluorescenceCaptureProgress.model_validate_json(str(body))
        self.model.running = True
        self.model.status = (
            f"Filter {p.filter_position} ({p.index + 1}/{p.total}): "
            f"{p.stage} {p.detail}".rstrip()
        )

    def _on_fluorescence_capture_done_triggered(self, body):
        done = FluorescenceCaptureDone.model_validate_json(str(body))
        self.model.running = False

        # A refusal carries directory="" — never overwrite the previous
        # run's saved-to folder with that.
        if done.directory:
            self.model.last_directory = done.directory

        if done.frames:
            self.model.record_results(done.frames)

        if done.error:
            self.model.status = f"FAILED: {done.error}"
        elif done.ok:
            self.model.status = f"{len(done.frames)} frame(s) saved"
        else:
            self.model.status = "FAILED: aborted"

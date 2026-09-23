# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fluorescence capture column — a step's fluorescence capture setup
(issue #695). A plain `Column`, not a compound: the cell holds a
`FluorescenceStepCapture` dict (or None), authored by the Fluorescence
Capture pane over PROTOCOL_TREE_SET_CELL rather than by an in-grid editor
(mirrors the PMT capture column).

`on_pre_step` runs the entries ticked `at_start`; `on_post_step` those
ticked `at_end` — a start capture is a baseline before the step's other
columns act (magnet/heater run in `on_step`), an end capture reads the
settled result. Each phase publishes one FLUORESCENCE_CAPTURE request
tagged with `request_id=f"{row.uuid}:{phase}"` and waits for the matching
FLUORESCENCE_CAPTURE_DONE, so a pane-initiated capture or a stale done can
never satisfy a step (the PMT capture column's `step_uuid`-style
correlation pattern).
"""

# Standard library imports.
import json
import re

# Enthought library imports.
from traits.api import Any, List, Str

# Microdrop package imports.
from pluggable_protocol_tree.consts import (
    protocol_logging_metadata_contribution_publisher,
)
from pluggable_protocol_tree.execution.exceptions import AbortError
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler,
    BaseColumnModel,
    Column,
)
from pluggable_protocol_tree.views.columns.base import BaseColumnView
from portable_dropbot_controller.consts import (
    FLUORESCENCE_CAPTURE_ABORT,
    FLUORESCENCE_CAPTURE_DONE,
    FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S,
    FLUORESCENCE_STEP_TIMEOUT_MARGIN_S,
    PMT_CAPTURE_LABEL_CHARS,
    PMT_CAPTURE_LABEL_MAX_LENGTH,
    fluorescence_capture_publisher,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..capture_exclusivity import check_single_capture
from ..consts import FLUORESCENCE_CAPTURE_COLUMN_ID
from ..fluorescence_step_capture import (
    normalize_step_capture,
    parse_step_capture,
    summary_text,
)
from ..step_capture import PHASE_END, PHASE_START, entries_for_phase

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Characters a capture label may not contain — the fluorescence request
#: reuses the PMT capture's filename-safe pattern (FluorescenceCaptureRequest
#: validates `label` against the same PMT_CAPTURE_LABEL_PATTERN).
_LABEL_DISALLOWED_CHARS = re.compile(f"[^{PMT_CAPTURE_LABEL_CHARS}]")


def _sanitize_label(label):
    return _LABEL_DISALLOWED_CHARS.sub("", label)[:PMT_CAPTURE_LABEL_MAX_LENGTH]


class FluorescenceStepCaptureColumnModel(BaseColumnModel):
    """The stored value is a `FluorescenceStepCapture` dict (or None);
    normalised (tick-filtered) on every write, whether from a cell edit or
    the pane's PROTOCOL_TREE_SET_CELL."""

    col_id = Str(FLUORESCENCE_CAPTURE_COLUMN_ID)
    col_name = Str("Fluorescence Capture")

    def trait_for_row(self):
        return Any(self.default_value)

    def set_value(self, row, value):
        setattr(row, self.col_id, normalize_step_capture(value))
        return True

    def deserialize(self, raw):
        # Tolerant like the PMT capture column: a stale or hand-edited
        # protocol file must never fail to load.
        return normalize_step_capture(raw)


class FluorescenceStepCaptureColumnView(BaseColumnView):
    """Display-only summary; the Fluorescence Capture pane owns authoring
    the cell, so this column has no in-grid editor."""

    #: The pane writes the cell over PROTOCOL_TREE_SET_CELL (bypassing
    #: setData), so declare the dependency for the tree model's per-row
    #: repaint wiring.
    depends_on_row_traits = List(Str, value=[FLUORESCENCE_CAPTURE_COLUMN_ID])

    def format_display(self, value, row):
        return summary_text(value)

    def create_editor(self, parent, context):
        return None


class FluorescenceCaptureHandler(BaseColumnHandler):
    """Runs the step's ticked fluorescence captures and blocks until each
    phase's capture is done.

    Priority 20 — the magnet/heater/PMT bucket; irrelevant across the
    pre/post-step hooks this handler uses, but keeps the column with its
    siblings. The ack wait comes from the Protocol Settings grid; the
    scalar only gates fire-and-forget (0 = publish, don't wait) — the
    actual per-phase timeout is computed from the entries themselves.
    """

    priority = 20
    wait_for_topics = [FLUORESCENCE_CAPTURE_DONE]
    default_ack_time_s = 60.0

    def on_pre_step(self, row, ctx):
        self._run_phase(row, ctx, PHASE_START)

    def on_post_step(self, row, ctx):
        self._run_phase(row, ctx, PHASE_END)

    def _run_phase(self, row, ctx, phase):
        if getattr(ctx.protocol, "preview_mode", False):
            return

        check_single_capture(row)

        step = parse_step_capture(getattr(row, FLUORESCENCE_CAPTURE_COLUMN_ID, None))

        if step is None:
            return

        entries = entries_for_phase(step, phase)

        if not entries:
            return

        request_id = f"{row.uuid}:{phase}"
        label = _sanitize_label(f"step{row.dotted_path()}-{phase}")

        logger.info(
            f"Starting fluorescence capture for step {row.dotted_path()} "
            f"({phase}, {len(entries)} filter(s))"
        )
        fluorescence_capture_publisher.publish(
            {
                "entries": [
                    {
                        "filter_position": e.filter_position,
                        "led_percent": e.led_percent,
                        "exposure_ms": e.exposure_ms,
                        "focus_distance": e.focus_distance,
                    }
                    for e in entries
                ],
                "request_id": request_id,
                "label": label,
                "directory": "",
                "park_motor": step.park_motor,
            }
        )

        if self.ack_time_s <= 0:
            return

        timeout = (
            len(entries) * FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S
            # Parking is one more wheel move after the last frame.
            + (FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S if step.park_motor else 0)
            + FLUORESCENCE_STEP_TIMEOUT_MARGIN_S
        )

        try:
            done_raw = ctx.wait_for(
                FLUORESCENCE_CAPTURE_DONE,
                timeout=timeout,
                predicate=lambda payload: (
                    json.loads(payload).get("request_id") == request_id
                ),
            )
        except AbortError:
            publish_message(topic=FLUORESCENCE_CAPTURE_ABORT, message="")
            raise

        done = json.loads(done_raw)
        self._contribute_to_report(done)

        if not done.get("ok"):
            raise RuntimeError(done.get("error") or "Fluorescence capture failed")

        logger.info(
            f"Finished fluorescence capture for step {row.dotted_path()} ({phase})"
        )

    def _contribute_to_report(self, done):
        """Put the captures folder into the run's report as a metadata
        link. The PNGs themselves reach the report's Media Captures
        section on their own through the device viewer's live
        DEVICE_VIEWER_MEDIA_CAPTURED publish, so no per-image
        contribution is needed here. Sent before the ok check so a partly
        failed capture still reports the folder it wrote into."""

        if done.get("directory"):
            protocol_logging_metadata_contribution_publisher.publish(
                {"Fluorescence Captures Folder": done["directory"]}
            )

    def on_post_protocol_end(self, ctx):
        # Unconditional, including in preview mode: an interrupted run
        # must never leave a capture going, and an abort with nothing
        # running is a no-op on the backend side.
        publish_message(topic=FLUORESCENCE_CAPTURE_ABORT, message="")


def make_fluorescence_capture_column():
    """Factory — a fresh fluorescence capture Column."""
    return Column(
        model=FluorescenceStepCaptureColumnModel(),
        view=FluorescenceStepCaptureColumnView(),
        handler=FluorescenceCaptureHandler(),
    )

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PMT capture column — a step's PMT capture setup (issue #601, increment
2). A plain `Column`, not a compound: the cell holds a `PmtStepCapture`
dict (or None), authored by the PMT Capture pane over
PROTOCOL_TREE_SET_CELL rather than by an in-grid editor (mirrors the
fluorescence capture-chain column).

`on_pre_step` runs the entries ticked `at_start`; `on_post_step` those
ticked `at_end` — a start capture is a baseline before the step's other
columns act (magnet/heater run in `on_step`), an end capture reads the
settled result. Each phase publishes one PMT_CAPTURE request tagged with
`request_id=f"{row.uuid}:{phase}"` and waits for the matching
PMT_CAPTURE_DONE, so a pane-initiated capture or a stale done can never
satisfy a step (the droplet-check `step_uuid` correlation pattern).
"""

# Standard library imports.
import json
import re
from pathlib import Path

# Enthought library imports.
from traits.api import Any, List, Str

# Microdrop package imports.
from pluggable_protocol_tree.consts import (
    protocol_logging_data_contribution_publisher,
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
    PMT_ADC_FULL_SCALE,
    PMT_CAPTURE_ABORT,
    PMT_CAPTURE_DONE,
    PMT_CAPTURE_LABEL_CHARS,
    PMT_CAPTURE_LABEL_MAX_LENGTH,
    PMT_RF_OHMS,
    PMT_STEP_PER_SPOT_OVERHEAD_S,
    PMT_STEP_TIMEOUT_MARGIN_S,
    PMT_VREF_V,
    pmt_capture_publisher,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..capture_exclusivity import check_single_capture
from ..consts import PMT_CAPTURE_COLUMN_ID
from ..pmt_step_capture import (
    PHASE_END,
    PHASE_START,
    entries_for_phase,
    normalize_step_capture,
    parse_step_capture,
    summary_text,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Characters a capture label may not contain, stripped from a step's
#: generated label (its dotted path is always digits/dots, so this only
#: guards against a future path-rendering change).
_LABEL_DISALLOWED_CHARS = re.compile(f"[^{PMT_CAPTURE_LABEL_CHARS}]")


def _sanitize_label(label):
    return _LABEL_DISALLOWED_CHARS.sub("", label)[:PMT_CAPTURE_LABEL_MAX_LENGTH]


class PmtStepCaptureColumnModel(BaseColumnModel):
    """The stored value is a `PmtStepCapture` dict (or None); normalised
    (tick-filtered) on every write, whether from a cell edit or the pane's
    PROTOCOL_TREE_SET_CELL."""

    col_id = Str(PMT_CAPTURE_COLUMN_ID)
    col_name = Str("PMT Capture")

    def trait_for_row(self):
        return Any(self.default_value)

    def set_value(self, row, value):
        setattr(row, self.col_id, normalize_step_capture(value))
        return True

    def deserialize(self, raw):
        # Tolerant like the fluorescence chain column: a stale or
        # hand-edited protocol file must never fail to load.
        return normalize_step_capture(raw)


class PmtStepCaptureColumnView(BaseColumnView):
    """Display-only summary; the PMT Capture pane owns authoring the
    cell, so this column has no in-grid editor."""

    #: The pane writes the cell over PROTOCOL_TREE_SET_CELL (bypassing
    #: setData), so declare the dependency for the tree model's per-row
    #: repaint wiring.
    depends_on_row_traits = List(Str, value=[PMT_CAPTURE_COLUMN_ID])

    def format_display(self, value, row):
        return summary_text(value)

    def create_editor(self, parent, context):
        return None


class PmtCaptureHandler(BaseColumnHandler):
    """Runs the step's ticked PMT captures and blocks until each phase's
    capture is done.

    Priority 20 — the magnet/heater bucket; irrelevant across the
    pre/post-step hooks this handler uses, but keeps the column with its
    siblings. The ack wait comes from the Protocol Settings grid; the
    scalar only gates fire-and-forget (0 = publish, don't wait) — the
    actual per-phase timeout is computed from the entries themselves.
    """

    priority = 20
    wait_for_topics = [PMT_CAPTURE_DONE]
    default_ack_time_s = 60.0

    def on_pre_step(self, row, ctx):
        self._run_phase(row, ctx, PHASE_START)

    def on_post_step(self, row, ctx):
        self._run_phase(row, ctx, PHASE_END)

    def _run_phase(self, row, ctx, phase):
        if getattr(ctx.protocol, "preview_mode", False):
            return

        check_single_capture(row)

        step = parse_step_capture(getattr(row, PMT_CAPTURE_COLUMN_ID, None))

        if step is None:
            return

        entries = entries_for_phase(step, phase)

        if not entries:
            return

        request_id = f"{row.uuid}:{phase}"
        label = _sanitize_label(f"step{row.dotted_path()}-{phase}")

        logger.info(
            f"Starting PMT capture for step {row.dotted_path()} "
            f"({phase}, {len(entries)} spot(s))"
        )
        pmt_capture_publisher.publish(
            {
                "avg": step.avg,
                "osr": step.osr,
                "rf_ohms": step.rf_ohms,
                "entries": [
                    {"slot": e.slot, "gain": e.gain, "exposure_s": e.exposure_s}
                    for e in entries
                ],
                "request_id": request_id,
                "label": label,
                "stop_live_stream": True,
            }
        )

        if self.ack_time_s <= 0:
            return

        timeout = (
            sum(e.exposure_s for e in entries)
            + len(entries) * PMT_STEP_PER_SPOT_OVERHEAD_S
            + PMT_STEP_TIMEOUT_MARGIN_S
        )

        try:
            done_raw = ctx.wait_for(
                PMT_CAPTURE_DONE,
                timeout=timeout,
                predicate=lambda payload: (
                    json.loads(payload).get("request_id") == request_id
                ),
            )
        except AbortError:
            publish_message(topic=PMT_CAPTURE_ABORT, message="")
            raise

        done = json.loads(done_raw)
        self._contribute_to_report(phase, done)

        if not done.get("ok"):
            raise RuntimeError(done.get("error") or "PMT capture failed")

        logger.info(f"Finished PMT capture for step {row.dotted_path()} ({phase})")

    def _contribute_to_report(self, phase, done):
        """Put the capture into the run's report: the captures folder as a
        metadata link, and one data row per spot (numeric columns feed the
        report's Data Summary and Data Trends). Sent before the ok check so
        a partly failed capture still reports the spots it saved; the step
        stamp comes from the logger."""

        if done.get("directory"):
            protocol_logging_metadata_contribution_publisher.publish(
                {"PMT Captures Folder": done["directory"]}
            )

        full_scale = done.get("adc_full_scale") or PMT_ADC_FULL_SCALE
        rf_ohms = done.get("rf_ohms") or PMT_RF_OHMS

        for result in done.get("results", []):
            mean_volts = result["mean_counts"] * PMT_VREF_V / full_scale
            csv_path = result.get("csv_path", "")

            protocol_logging_data_contribution_publisher.publish(
                {
                    "PMT phase": phase,
                    "PMT spot": result["slot"],
                    "PMT gain": result["gain"],
                    "PMT exposure (s)": result["exposure_s"],
                    "PMT samples": result["n_samples"],
                    "PMT mean (counts)": result["mean_counts"],
                    "PMT mean (V)": mean_volts,
                    "PMT mean (A)": mean_volts / rf_ohms,
                    "PMT file": Path(csv_path).name if csv_path else "",
                    "PMT error": result.get("error", ""),
                }
            )

    def on_post_protocol_end(self, ctx):
        # Unconditional: an interrupted run must never leave a capture
        # going. Preview runs have no hardware side effects to clean up.
        if getattr(ctx, "preview_mode", False):
            return

        publish_message(topic=PMT_CAPTURE_ABORT, message="")


def make_pmt_capture_column():
    """Factory — a fresh PMT capture Column."""
    return Column(
        model=PmtStepCaptureColumnModel(),
        view=PmtStepCaptureColumnView(),
        handler=PmtCaptureHandler(),
    )

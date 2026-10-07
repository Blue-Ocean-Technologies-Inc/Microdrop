# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Capture compound column — one-shot screen capture per step. Three
coupled cells (capture Bool, capture_at Step Start / Step End choice,
capture_lead_ms camera lead time) sharing one model + one handler via
the PPT-11 compound framework (#396).

Timing is PER STEP: each row picks start-of-step or end-of-step capture
independently; newly added steps start at Step Start.

Camera lead: when capture_lead_ms > 0 the handler turns the camera on
(DEVICE_VIEWER_CAMERA_ACTIVE "true") at step start and holds the capture
until the camera has been on for at least that long — a stop-aware sleep
of the full lead for Step Start, of only the unelapsed remainder for
Step End. A lead of 0 leaves the camera alone and captures without
waiting.

Camera ownership: Capture keeps its own camera-on state
(CAPTURE_CAMERA_ON_KEY) and never writes the Video column's
VIDEO_CAMERA_ON_KEY. A lead's camera-on stays on for the rest of the run
unless the Video column switches it off; at protocol end Capture switches
it off only if Video does not want it on. Running after VideoHandler
(priority 11 vs 10) publishes Video's "false" before the lead's "true"
on a step where Video flips off, but both publishes on the one topic are
delivered by concurrent frontend workers, so that ordering is
best-effort. That is why Capture never feeds Video's change detection: a
"false" that Video derived from Capture's state could land after the
lead's "true" and leave the camera off for the whole lead.

Fire-and-forget — DEVICE_VIEWER_SCREEN_CAPTURE has no ack topic.

Capture payload format:
    {"directory": experiment_dir, "step_description": ..., "step_id": ...,
     "show_status_message": false}

⚠ Key is "directory" (NOT "experiment_dir") — preserves the legacy wire
format the device_viewer consumer expects.
"""

# Standard library imports.
import json
import time

# Enthought library imports.
from pyface.qt.QtCore import Qt
from traits.api import Bool, Enum, Int, List, Str

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_ACTIVE,
    DEVICE_VIEWER_SCREEN_CAPTURE,
)
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler,
    BaseCompoundColumnModel,
    CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.combobox import ComboBoxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView
from video_protocol_controls.consts import EXPERIMENT_DIR_SCRATCH_KEY, StepTime
from video_protocol_controls.protocol_columns.video_column import (
    VIDEO_CAMERA_ON_KEY,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

#: The selectable capture moments, in display order — the single
#: definition; the default/per-row trait validation and the
#: combobox options all derive from it.
CHOICES = (StepTime.START, StepTime.END)

#: Cross-step scratch entry: True once a lead has switched the camera on
#: in this run; on_protocol_end switches it off unless Video owns it.
CAPTURE_CAMERA_ON_KEY = "video_protocol_controls.capture_camera_on"

#: Per-step scratch entry: time.monotonic() at which this step's lead
#: turned the camera on; consumed (popped) when the capture fires.
CAMERA_ON_AT_SCRATCH_KEY = "video_protocol_controls.capture_camera_on_at"


class CaptureCompoundModel(BaseCompoundColumnModel):
    """Three coupled fields. base_id 'capture' appears as compound_id on
    each field's column entry in JSON (PPT-11 framework)."""

    base_id = "capture"

    # Default capture_at for newly added steps (and the fill-in for any
    # payload missing the field): Step Start, the first choice.
    default_capture_at = Enum(*CHOICES)

    def field_specs(self):
        return [
            FieldSpec("capture", "Capture", False),
            FieldSpec("capture_at", "Capture At", self.default_capture_at),
            FieldSpec("capture_lead_ms", "Camera Lead (ms)", 0),
        ]

    def trait_for_field(self, field_id):
        if field_id == "capture":
            return Bool(False, desc="Capture image during step")

        if field_id == "capture_at":
            return Enum(
                self.default_capture_at,
                *CHOICES,
                desc="When during the step the capture fires",
            )

        if field_id == "capture_lead_ms":
            return Int(0, desc="Milliseconds the camera is on before the capture fires")

        raise KeyError(field_id)


class CaptureAtComboBoxView(ComboBoxColumnView):
    """Read-only while row.capture is False — capture_at is meaningless
    when the step doesn't capture (cross-cell editability via the
    canonical PPT-11 get_flags(row) pattern, mirroring the magnet
    height cell)."""

    #: get_flags/format_display above are pure functions of row.capture;
    #: declare it so the tree model repaints this cell the moment the
    #: checkbox toggles (issue #541 latent bug — previously the grey-out
    #: waited for an incidental repaint).
    depends_on_row_traits = List(Str, value=["capture"])

    def _options_default(self):
        return list(CHOICES)

    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, "capture", False):
            flags &= ~Qt.ItemIsEditable
        return flags

    def format_display(self, value, row):
        # An empty cell reads better than a stale choice on rows that
        # don't capture.
        if not getattr(row, "capture", False):
            return ""
        return super().format_display(value, row)


class CaptureLeadSpinBoxView(IntSpinBoxColumnView):
    """Read-only and blank while row.capture is False — a camera lead is
    meaningless when the step doesn't capture (same cross-cell pattern as
    CaptureAtComboBoxView)."""

    #: get_flags/format_display are pure functions of row.capture; repaint
    #: the cell the moment the checkbox toggles.
    depends_on_row_traits = List(Str, value=["capture"])

    low = 0
    high = 60000

    def get_flags(self, row):
        flags = super().get_flags(row)

        if not getattr(row, "capture", False):
            flags &= ~Qt.ItemIsEditable

        return flags

    def format_display(self, value, row):
        if not getattr(row, "capture", False):
            return ""

        return super().format_display(value, row)


class CaptureHandler(BaseCompoundColumnHandler):
    """Publishes a single image-capture event per step where row.capture
    is True, at the row's chosen moment (row.capture_at), after the
    row's camera lead (row.capture_lead_ms) has elapsed.

    Priority 11 — one bucket after Video and Record (10), whose hooks run
    in parallel with each other. On a step where Video flips off, this
    publishes VideoHandler's "false" before the lead's "true" rather than
    alongside it; still ahead of V/F (20) and routes (30).

    Cross-step state is CAPTURE_CAMERA_ON_KEY only (Video's key is never
    written — see the module docstring); the camera-on time is per-step
    scratch, consumed when the capture fires. There is no
    change-detection suppression, so calling on_pre_step twice with
    row.capture=True fires two publishes.
    """

    priority = 11
    # No wait_for_topics — fire-and-forget; list stays empty (inherited default).

    def on_pre_step(self, row, ctx):
        """Turn the camera on for a lead, and fire now when the row's
        capture_at says Step Start.

        `ctx` here is a StepContext; protocol-scoped scratch is accessed via
        `ctx.protocol.scratch`.
        """
        if not getattr(row, "capture", False):
            return

        lead_ms = getattr(row, "capture_lead_ms", 0)

        if lead_ms > 0:
            self._turn_camera_on(ctx)

        if getattr(row, "capture_at", StepTime.START) != StepTime.START:
            return

        self._wait_out_lead(lead_ms, ctx)
        self._fire_capture(row, ctx)

    def on_post_step(self, row, ctx):
        """Fire at step end when the row's capture_at says Step End.

        `ctx` here is a StepContext; protocol-scoped scratch is accessed via
        `ctx.protocol.scratch`.
        """
        if not getattr(row, "capture", False):
            return

        if getattr(row, "capture_at", StepTime.START) != StepTime.END:
            return

        self._wait_out_lead(getattr(row, "capture_lead_ms", 0), ctx)
        self._fire_capture(row, ctx)

    def on_protocol_end(self, ctx):
        """Switch off a camera a lead left on, unless Video wants it on.

        `ctx` here is a ProtocolContext; scratch is accessed directly via
        `ctx.scratch` (not `ctx.protocol.scratch`).
        """
        if not ctx.scratch.get(CAPTURE_CAMERA_ON_KEY, False):
            return

        if not ctx.scratch.get(VIDEO_CAMERA_ON_KEY, False):
            publish_message(topic=DEVICE_VIEWER_CAMERA_ACTIVE, message="false")

        ctx.scratch[CAPTURE_CAMERA_ON_KEY] = False

    def _turn_camera_on(self, ctx):
        """Switch the camera on and record when, for the lead wait."""
        # Unconditional: the device viewer's turn-on is a no-op when the
        # feed is already live.
        publish_message(topic=DEVICE_VIEWER_CAMERA_ACTIVE, message="true")

        ctx.protocol.scratch[CAPTURE_CAMERA_ON_KEY] = True
        ctx.protocol.scratch[CAMERA_ON_AT_SCRATCH_KEY] = time.monotonic()

    def _wait_out_lead(self, lead_ms, ctx):
        """Sleep until the camera has been on for lead_ms (stop-aware)."""
        camera_on_at = ctx.protocol.scratch.pop(CAMERA_ON_AT_SCRATCH_KEY, None)

        if lead_ms <= 0 or camera_on_at is None:
            return

        elapsed = time.monotonic() - camera_on_at

        ctx.protocol.sleep(max(0.0, lead_ms / 1000 - elapsed))

    def _fire_capture(self, row, ctx):
        """Build the legacy-compatible payload and publish it."""
        payload = {
            "directory": ctx.protocol.scratch.get(EXPERIMENT_DIR_SCRATCH_KEY, ""),
            "step_description": row.name,
            "step_id": row.dotted_path(),
            "show_status_message": False,
        }
        publish_message(
            topic=DEVICE_VIEWER_SCREEN_CAPTURE,
            message=json.dumps(payload),
        )


def make_capture_column():
    """Return a fresh Capture compound column (capture, capture_at,
    capture_lead_ms)."""
    return CompoundColumn(
        model=CaptureCompoundModel(),
        view=DictCompoundColumnView(
            cell_views={
                "capture": CheckboxColumnView(),
                "capture_at": CaptureAtComboBoxView(),
                "capture_lead_ms": CaptureLeadSpinBoxView(),
            }
        ),
        handler=CaptureHandler(),
    )

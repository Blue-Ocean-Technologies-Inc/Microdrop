"""Capture compound column — one-shot screen capture per step. Two
coupled cells (capture Bool + capture_at Step Start / Step End choice)
sharing one model + one handler via the PPT-11 compound framework (#396).

Timing is PER STEP: each row picks start-of-step or end-of-step capture
independently. The global ProtocolPreferences.capture_time pref is the
DEFAULT for newly added steps (read once at factory time) — it never
overrides a per-step value.

Fire-and-forget — DEVICE_VIEWER_SCREEN_CAPTURE has no ack topic; the
legacy code in protocol_grid/services/utils.py is also fire-and-forget.

Capture payload format (legacy-compatible — see protocol_grid/services/
utils.py:19-32):
    {"directory": experiment_dir, "step_description": ..., "step_id": ...,
     "show_dialog": false}

⚠ Key is "directory" (NOT "experiment_dir") — preserves the legacy wire
format the device_viewer consumer expects.

This handler has no cross-step state — capture is per-step, not bracketed
like Record or Video. So no scratch key needed; no on_protocol_end cleanup
needed.
"""

import json

from pyface.qt.QtCore import Qt
from traits.api import Bool, Enum, List

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from device_viewer.consts import DEVICE_VIEWER_SCREEN_CAPTURE
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.services.preferences import (
    ProtocolPreferences, StepTime,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.combobox import ComboBoxColumnView
from video_protocol_controls.consts import EXPERIMENT_DIR_SCRATCH_KEY

#: The selectable capture moments, in display order — the single
#: definition; the default/per-row trait validation and the
#: combobox options all derive from it.
CHOICES = (StepTime.START, StepTime.END)

class CaptureCompoundModel(BaseCompoundColumnModel):
    """Two coupled fields. base_id 'capture' appears as compound_id on
    each field's column entry in JSON (PPT-11 framework)."""
    base_id = "capture"

    # Default capture_at for newly added steps (and the fill-in for any
    # payload missing the field). The factory seeds it from
    # ProtocolPreferences.capture_time.
    default_capture_at = Enum(*CHOICES)

    def field_specs(self):
        return [
            FieldSpec("capture", "Capture", False),
            FieldSpec("capture_at", "Capture At", self.default_capture_at),
        ]

    def trait_for_field(self, field_id):
        if field_id == "capture":
            return Bool(False, desc="Capture image during step")
        if field_id == "capture_at":
            return Enum(self.default_capture_at,
                        *CHOICES,
                        desc="When during the step the capture fires")
        raise KeyError(field_id)


class CaptureAtComboBoxView(ComboBoxColumnView):
    """Read-only while row.capture is False — capture_at is meaningless
    when the step doesn't capture (cross-cell editability via the
    canonical PPT-11 get_flags(row) pattern, mirroring the magnet
    height cell)."""

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


class CaptureHandler(BaseCompoundColumnHandler):
    """Publishes a single image-capture event per step where row.capture
    is True, at the row's chosen moment (row.capture_at).

    Priority 10 — same earliest bucket as Video and Record, since the three
    fire to independent topics and parallel execution is safe (see notes in
    VideoHandler / RecordHandler about priority-10 cleanup parallelism;
    Capture has no on_protocol_end so it's not even part of that race).

    This handler has no cross-step state (no scratch key). Each step is
    fully independent — if row.capture is True, the event fires; if False,
    it doesn't. There is no change-detection suppression, so calling
    on_pre_step twice with row.capture=True fires two publishes.
    """
    priority = 10
    # No wait_for_topics — fire-and-forget; list stays empty (inherited default).

    def on_pre_step(self, row, ctx):
        """Fire at step start when the row's capture_at says Step Start.

        `ctx` here is a StepContext; protocol-scoped scratch is accessed via
        `ctx.protocol.scratch`.
        """
        if not getattr(row, "capture", False):
            return
        if getattr(row, "capture_at", StepTime.START) != StepTime.START:
            return
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
        self._fire_capture(row, ctx)

    def _fire_capture(self, row, ctx):
        """Build the legacy-compatible payload and publish it."""
        payload = {
            "directory": ctx.protocol.scratch.get(EXPERIMENT_DIR_SCRATCH_KEY, ""),
            "step_description": row.name,
            "step_id": row.dotted_path(),
            "show_dialog": False,
        }
        publish_message(
            topic=DEVICE_VIEWER_SCREEN_CAPTURE,
            message=json.dumps(payload),
        )


def make_capture_column():
    """Return a fresh Capture compound column (capture + capture_at).

    ProtocolPreferences.capture_time is read once at call time and
    becomes the capture_at default for newly added steps; per-step edits
    are never overridden by the pref.
    """
    prefs = ProtocolPreferences()
    model = CaptureCompoundModel(default_capture_at=prefs.capture_time)
    return CompoundColumn(
        model=model,
        view=DictCompoundColumnView(cell_views={
            "capture": CheckboxColumnView(),
            "capture_at": CaptureAtComboBoxView(),
        }),
        handler=CaptureHandler(),
    )

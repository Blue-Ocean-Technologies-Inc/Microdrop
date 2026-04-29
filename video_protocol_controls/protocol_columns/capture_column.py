"""Capture column — Bool checkbox; one-shot screen capture per step
where row.capture is True. Timing (step start vs step end) is controlled
by the global ProtocolPreferences.capture_time pref, read ONCE at handler
construction (factory time). Fire-and-forget — DEVICE_VIEWER_SCREEN_CAPTURE
has no ack topic; the legacy code in protocol_grid/services/utils.py is
also fire-and-forget.

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

from traits.api import Bool

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from device_viewer.consts import DEVICE_VIEWER_SCREEN_CAPTURE
from protocol_grid.preferences import ProtocolPreferences, StepTime


class CaptureColumnModel(BaseColumnModel):
    """Per-step capture flag stored as a Bool on each row."""

    def trait_for_row(self):
        return Bool(bool(self.default_value), desc="Capture image during step")


class CaptureHandler(BaseColumnHandler):
    """Publishes a single image-capture event per step where row.capture is True.

    Priority 10 — same earliest bucket as Video and Record, since the three
    fire to independent topics and parallel execution is safe (see notes in
    VideoHandler / RecordHandler about priority-10 cleanup parallelism;
    Capture has no on_protocol_end so it's not even part of that race).

    Fire timing is fixed at handler construction by reading
    ProtocolPreferences().capture_time. Mid-protocol pref edits do NOT take
    effect — matches PPT-4's voltage column which similarly snapshots the
    last_voltage pref at factory time. To pick up a new pref, recreate the
    column (which happens on plugin re-load).

    This handler has no cross-step state (no scratch key). Each step is
    fully independent — if row.capture is True, the event fires; if False,
    it doesn't. There is no change-detection suppression, so calling
    on_pre_step twice with row.capture=True fires two publishes.
    """
    priority = 10
    # No wait_for_topics — fire-and-forget; list stays empty (inherited default).

    # Declared at class level as a Trait so HasTraits constructor kwargs
    # (e.g. CaptureHandler(fire_at_start=False)) work correctly.
    # Default True → fire at step start; False → fire at step end.
    fire_at_start = Bool(True)

    def on_pre_step(self, row, ctx):
        """Fire capture at step start when fire_at_start is True.

        `ctx` here is a StepContext; protocol-scoped scratch is accessed via
        `ctx.protocol.scratch`.
        """
        if not self.fire_at_start:
            return
        if not bool(row.capture):
            return
        self._fire_capture(row, ctx)

    def on_post_step(self, row, ctx):
        """Fire capture at step end when fire_at_start is False.

        `ctx` here is a StepContext; protocol-scoped scratch is accessed via
        `ctx.protocol.scratch`.
        """
        if self.fire_at_start:
            return
        if not bool(row.capture):
            return
        self._fire_capture(row, ctx)

    def _fire_capture(self, row, ctx):
        """Build the legacy-compatible payload and publish it."""
        payload = {
            "directory": ctx.protocol.scratch.get("experiment_dir", ""),
            "step_description": row.name,
            "step_id": row.uuid,
            "show_dialog": False,
        }
        publish_message(
            topic=DEVICE_VIEWER_SCREEN_CAPTURE,
            message=json.dumps(payload),
        )


def make_capture_column():
    """Return a fresh Capture column instance (model + checkbox view + handler).

    Reads ProtocolPreferences().capture_time once at call time and stores it
    as fire_at_start on the handler. Mid-protocol pref changes do not affect
    a running protocol — recreate the column to pick up a new pref value.
    """
    prefs = ProtocolPreferences()
    return Column(
        model=CaptureColumnModel(
            col_id="capture",
            col_name="Capture",
            default_value=False,
        ),
        view=CheckboxColumnView(),
        handler=CaptureHandler(
            fire_at_start=(prefs.capture_time == StepTime.START),
        ),
    )

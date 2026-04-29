"""Record column — Bool checkbox; bracketing semantics: publish a JSON start
payload to DEVICE_VIEWER_SCREEN_RECORDING on flip-on, publish a stop payload on
flip-off.  Cross-step state is tracked via ctx.protocol.scratch so
change-detection survives across multiple steps of the same protocol run.

Bracketing semantics in detail:
  - flip-on  (False → True):  publish {"action": "start", "directory": ...,
                                         "step_description": ..., "step_id": ...,
                                         "show_dialog": false}
  - flip-off (True → False):  publish {"action": "stop"}
  - on_protocol_end:           if recording was left active, publish {"action": "stop"}
                                and reset scratch — ensures the consumer is never
                                left in a recording state after the run finishes.

Legacy wire format reference: protocol_grid/services/utils.py:34-52.
⚠ The key is "directory" (NOT "experiment_dir") — the device_viewer consumer
expects the legacy key; do not change it.

Convention for cross-step scratch keys in this plugin: dot-namespaced as
'video_protocol_controls.<state_var>' so Tasks 3 (Video) and 5 (Capture)
can add their own keys without colliding with each other or with any other
plugin's scratch entries (e.g. routes_column's DURATION_CONSUMED_KEY).
"""

import json

from traits.api import Bool

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from device_viewer.consts import DEVICE_VIEWER_SCREEN_RECORDING


RECORDING_ACTIVE_KEY = "video_protocol_controls.record_active"


class RecordColumnModel(BaseColumnModel):
    """Per-step record flag stored as a Bool on each row."""

    def trait_for_row(self):
        return Bool(bool(self.default_value), desc="Record video during step")


class RecordHandler(BaseColumnHandler):
    """Publishes screen-recording start/stop only when the value flips.

    Priority 10 — runs in the earliest bucket so recording starts before
    V/F (priority 20) or RoutesHandler (priority 30).  Fire-and-forget —
    DEVICE_VIEWER_SCREEN_RECORDING has no ack topic; the legacy code in
    protocol_grid/services/utils.py is also fire-and-forget.

    Cross-step state is held in ctx.protocol.scratch[RECORDING_ACTIVE_KEY]
    so the change-detection survives across multiple steps of the same
    protocol run, and is reset cleanly between runs (scratch is per-run).
    """
    priority = 10
    # No wait_for_topics — fire-and-forget; list stays empty (inherited default).

    def on_pre_step(self, row, ctx):
        """Publish recording start/stop only when the record flag flips.

        `ctx` here is a StepContext; protocol-scoped scratch is accessed via
        `ctx.protocol.scratch`.
        """
        desired = bool(row.record)
        last = bool(ctx.protocol.scratch.get(RECORDING_ACTIVE_KEY, False))
        if desired == last:
            return

        if desired and not last:
            # Flip-on: send the start payload with step metadata + experiment dir.
            payload = {
                "action": "start",
                "directory": ctx.protocol.scratch.get("experiment_dir", ""),
                "step_description": row.name,
                "step_id": row.uuid,
                "show_dialog": False,
            }
            publish_message(
                topic=DEVICE_VIEWER_SCREEN_RECORDING,
                message=json.dumps(payload),
            )
        else:
            # Flip-off: send the stop payload.
            publish_message(
                topic=DEVICE_VIEWER_SCREEN_RECORDING,
                message=json.dumps({"action": "stop"}),
            )

        ctx.protocol.scratch[RECORDING_ACTIVE_KEY] = desired

    def on_protocol_end(self, ctx):
        """Stop recording if the protocol ended with recording still active.

        `ctx` here is a ProtocolContext; scratch is accessed directly via
        `ctx.scratch` (not `ctx.protocol.scratch`).
        """
        if ctx.scratch.get(RECORDING_ACTIVE_KEY, False):
            publish_message(
                topic=DEVICE_VIEWER_SCREEN_RECORDING,
                message=json.dumps({"action": "stop"}),
            )
            ctx.scratch[RECORDING_ACTIVE_KEY] = False


def make_record_column():
    """Return a fresh Record column instance (model + checkbox view + handler)."""
    return Column(
        model=RecordColumnModel(
            col_id="record",
            col_name="Record",
            default_value=False,
        ),
        view=CheckboxColumnView(),
        handler=RecordHandler(),
    )

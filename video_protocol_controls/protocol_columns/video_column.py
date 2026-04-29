"""Video column — Bool checkbox; on flip-on publish DEVICE_VIEWER_CAMERA_ACTIVE
'true', on flip-off publish 'false'. Cross-step state via ctx.protocol.scratch.
Fire-and-forget — the camera widget has no ack topic for this state change.
"""

from traits.api import Bool

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from device_viewer.consts import DEVICE_VIEWER_CAMERA_ACTIVE


_SCRATCH_KEY = "video_camera_on"


class VideoColumnModel(BaseColumnModel):
    """Per-step camera-on flag stored as a Bool on each row."""

    def trait_for_row(self):
        return Bool(bool(self.default_value), desc="Live camera feed during step")


class VideoHandler(BaseColumnHandler):
    """Publishes camera on/off only when the value flips between steps.

    Priority 10 — runs in the earliest bucket so the camera is on
    before V/F (priority 20) or RoutesHandler (priority 30). Fire and
    forget — DEVICE_VIEWER_CAMERA_ACTIVE has no ack topic; the legacy
    code in protocol_grid/services/utils.py is also fire-and-forget.

    Cross-step state is held in ctx.protocol.scratch[_SCRATCH_KEY] so
    that the change-detection survives across multiple steps of the same
    protocol run, and is reset cleanly between runs.
    """
    priority = 10
    # No wait_for_topics — fire-and-forget; list stays empty (inherited default).

    def on_pre_step(self, row, ctx):
        """Publish camera state only when it flips from the previous step.

        `ctx` here is a StepContext; protocol-scoped scratch is accessed via
        `ctx.protocol.scratch`.
        """
        desired = bool(row.video)
        last = bool(ctx.protocol.scratch.get(_SCRATCH_KEY, False))
        if desired == last:
            return
        publish_message(
            topic=DEVICE_VIEWER_CAMERA_ACTIVE,
            message="true" if desired else "false",
        )
        ctx.protocol.scratch[_SCRATCH_KEY] = desired

    def on_protocol_end(self, ctx):
        """Turn the camera off if the protocol ended with it on.

        `ctx` here is a ProtocolContext; scratch is accessed directly via
        `ctx.scratch` (not `ctx.protocol.scratch`).
        """
        if ctx.scratch.get(_SCRATCH_KEY, False):  # camera left on
            publish_message(
                topic=DEVICE_VIEWER_CAMERA_ACTIVE,
                message="false",
            )
            ctx.scratch[_SCRATCH_KEY] = False


def make_video_column():
    return Column(
        model=VideoColumnModel(
            col_id="video",
            col_name="Video",
            default_value=False,
        ),
        view=CheckboxColumnView(),
        handler=VideoHandler(),
    )

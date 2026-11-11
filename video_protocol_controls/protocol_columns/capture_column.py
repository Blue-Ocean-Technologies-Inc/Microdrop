# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Capture compound column — one-shot screen capture per step. Four
coupled cells (capture Bool, capture_at Step Start / Step End choice,
capture_lead_ms camera lead time, capture_camera_settings camera setup)
sharing one model + one handler via the PPT-11 compound framework (#396).

Camera setup: each capturing step stores the resolution and camera
properties it captures with (a device_viewer CameraSettings dict), so they
may vary from step to step. The cell is display-only — the setup is taken
from the device viewer's camera panel: a user edit there is stored into
the selected capturing steps, and selecting such a step applies its setup
to the camera (services/camera_settings_sync.py). At run time the handler
applies the step's setup at step start, before the camera lead and the
capture; what the camera cannot take (an unsupported resolution, a missing
or out-of-range property) is skipped, the device viewer warning the user,
and the capture goes ahead with the camera's own values.

Timing is PER STEP: each row picks start-of-step or end-of-step capture
independently; newly added steps start at Step Start.

Camera lead: when capture_lead_ms > 0 the handler holds the capture
until the camera has been on for at least that long — a stop-aware sleep
of the full lead for Step Start, of only the unelapsed remainder for
Step End. A lead of 0 captures without waiting.

Camera ownership: the Video column is the single publisher of camera
state during a run (see video_column.camera_wanted). Capture contributes
the lead as a reason a step wants the camera, and only waits.

Another column may still choose the camera SOURCE around the run, with
DEVICE_VIEWER_CAMERA_SELECT_SOURCE (answered on
DEVICE_VIEWER_CAMERA_SOURCE_SELECTED): at run start, optionally with
active=True, and at run end to restore the DEVICE_VIEWER_CAMERA_STATE it
saw before — never per step. A select_source with active=True LEASES the
camera to the run: while leased, the device viewer ignores this column's
camera_active "false" (logged "Camera kept on: leased by a protocol
run"), so a step without video cannot stop the run's feed; "true" still
applies. The next select_source (the run-end restore, whatever it
carries) releases the lease, and so does PROTOCOL_RUNNING "False", so a
crashed run never leaves it held. Send the restore from
on_post_protocol_end: the Video column's on_protocol_end "false" is then
published while the lease still holds, and is ignored if it arrives
before the restore — Dramatiq does not order delivery across messages,
so one arriving after it still applies.

Acknowledged capture: each capture carries a fresh request_id and the
handler waits for the DEVICE_VIEWER_MEDIA_CAPTURED with that request_id,
so the step does not end until the image is on disk. Without the wait,
the next step's camera-off (or any later message) can overtake the frame
grab in the frontend's queue — observed live, with the device viewer
then re-arming the camera for its own warm-up. The wait is the Protocol
Settings ack grid value; 0 restores fire-and-forget.

Capture payload format:
    {"directory": experiment_dir, "step_description": ..., "step_id": ...,
     "show_status_message": false, "request_id": ...}

⚠ Key is "directory" (NOT "experiment_dir") — preserves the legacy wire
format the device_viewer consumer expects.
"""

# Standard library imports.
import json
import time
import uuid

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from pyface.qt.QtCore import Qt
from traits.api import Any, Bool, Enum, Int, List, Str

# Microdrop package imports.
from device_viewer.consts import (
    COMMON_RESOLUTION_NAMES,
    DEVICE_VIEWER_CAMERA_SETTINGS_APPLIED,
    DEVICE_VIEWER_MEDIA_CAPTURED,
    DEVICE_VIEWER_SCREEN_CAPTURE,
    CameraSettings,
    camera_apply_settings_publisher,
)
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler,
    BaseCompoundColumnModel,
    CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.base import BaseColumnView
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.combobox import ComboBoxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView
from video_protocol_controls.consts import (
    CAPTURE_CAMERA_SETTINGS_FIELD_ID,
    CAPTURE_FIELD_ID,
    EXPERIMENT_DIR_SCRATCH_KEY,
    StepTime,
)

# Microdrop utils imports.
from microdrop_utils.camera_image_controls import IMAGE_CONTROL_LABELS
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The selectable capture moments, in display order — the single
#: definition; the default/per-row trait validation and the
#: combobox options all derive from it.
CHOICES = (StepTime.START, StepTime.END)

#: Per-step scratch entry: time.monotonic() at which this step's lead
#: started, just after VideoHandler's camera-on request; consumed (popped)
#: when the capture fires.
CAMERA_ON_AT_SCRATCH_KEY = "video_protocol_controls.capture_camera_on_at"


def normalize_camera_settings(raw):
    """A stored camera setup as a JSON-native CameraSettings dict, or None
    for no setup — also for a stale or hand-edited one, which must never
    fail a protocol load."""
    if not raw:
        return None

    try:
        return CameraSettings.model_validate(raw).model_dump(mode="json")
    except ValidationError as error:
        logger.warning(f"Dropped an invalid capture camera setup {raw!r}: {error}")

        return None


def resolution_text(resolution):
    """'FHD (1920x1080)', or '1920x1080' for a size without a common name."""
    width, height = resolution
    name = COMMON_RESOLUTION_NAMES.get((width, height))
    size = f"{width}x{height}"

    return f"{name} ({size})" if name else size


class CaptureCompoundModel(BaseCompoundColumnModel):
    """Four coupled fields. base_id 'capture' appears as compound_id on
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
            FieldSpec(CAPTURE_CAMERA_SETTINGS_FIELD_ID, "Camera Settings", None),
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

        if field_id == CAPTURE_CAMERA_SETTINGS_FIELD_ID:
            return Any(None, desc="Camera resolution and properties of the capture")

        raise KeyError(field_id)

    def deserialize(self, field_id, raw):
        if field_id == CAPTURE_CAMERA_SETTINGS_FIELD_ID:
            return normalize_camera_settings(raw)

        return super().deserialize(field_id, raw)


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


class CaptureCameraSettingsView(BaseColumnView):
    """Display-only summary of the step's camera setup — its resolution,
    the properties in the tooltip; blank while row.capture is False. The
    device viewer's camera panel authors the setup (see the module
    docstring), so the cell has no editor."""

    #: The setup is written over PROTOCOL_TREE_SET_CELL (bypassing setData),
    #: and the display is a function of row.capture too.
    depends_on_row_traits = List(
        Str, value=[CAPTURE_FIELD_ID, CAPTURE_CAMERA_SETTINGS_FIELD_ID]
    )

    def format_display(self, value, row):
        if not getattr(row, CAPTURE_FIELD_ID, False) or not value:
            return ""

        if value["resolution"] is None:
            return "Camera defaults"

        return resolution_text(value["resolution"])

    def get_tooltip(self, row):
        settings = getattr(row, CAPTURE_CAMERA_SETTINGS_FIELD_ID, None)

        if not getattr(row, CAPTURE_FIELD_ID, False):
            return None

        if not settings:
            return (
                "No camera settings yet: they are taken from the device "
                "viewer's camera panel"
            )

        lines = [f"Camera: {settings['camera'] or 'any'}"]

        if settings["resolution"] is not None:
            lines.append(f"Resolution: {resolution_text(settings['resolution'])}")

        for name, control in settings["image_controls"].items():
            value = "auto" if control["auto"] else control["value"]
            lines.append(f"{IMAGE_CONTROL_LABELS.get(name, name)}: {value}")

        focus = settings["focus"]

        if focus is not None:
            value = "auto" if focus["auto"] else f"{focus['distance']:.2f}"
            lines.append(f"Focus: {value}")

        return "\n".join(lines)

    def create_editor(self, parent, context):
        return None


class CaptureHandler(BaseCompoundColumnHandler):
    """Publishes a single image-capture event per step where row.capture
    is True, at the row's chosen moment (row.capture_at), after the
    row's camera lead (row.capture_lead_ms) has elapsed, and blocks until
    the device viewer acknowledges the saved image (request_id match on
    DEVICE_VIEWER_MEDIA_CAPTURED). TimeoutError and AbortError propagate;
    an ack time of 0 publishes without waiting.

    Priority 11 — one bucket after Video and Record (10): Video has
    already published this step's camera state when the lead wait starts,
    so the lead counts from after the camera-on request; still ahead of
    V/F (20) and routes (30).

    No cross-step state; the camera-on time is per-step scratch, consumed
    when the capture fires. There is no change-detection suppression, so
    calling on_pre_step twice with row.capture=True fires two publishes.
    """

    priority = 11
    wait_for_topics = [
        DEVICE_VIEWER_MEDIA_CAPTURED,
        DEVICE_VIEWER_CAMERA_SETTINGS_APPLIED,
    ]
    default_ack_time_s = 15.0

    def on_pre_step(self, row, ctx):
        """Start the lead clock, and fire now when the row's capture_at
        says Step Start.

        `ctx` here is a StepContext; protocol-scoped scratch is accessed via
        `ctx.protocol.scratch`.
        """
        if not getattr(row, "capture", False):
            return

        # Before the lead clock starts: a new resolution restarts the stream.
        self._apply_camera_settings(row, ctx)

        lead_ms = getattr(row, "capture_lead_ms", 0)

        if lead_ms > 0:
            # VideoHandler (priority 10) has already asked for the camera.
            ctx.protocol.scratch[CAMERA_ON_AT_SCRATCH_KEY] = time.monotonic()

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

    def _apply_camera_settings(self, row, ctx):
        """Apply the step's camera setup, if it has one, and wait for the
        device viewer's answer. Nothing the camera cannot take stops the
        step: the device viewer warns the user and the capture goes ahead,
        so it is only logged here."""
        settings = getattr(row, CAPTURE_CAMERA_SETTINGS_FIELD_ID, None)

        if not settings:
            return

        request_id = uuid.uuid4().hex
        context = f"Step {row.dotted_path()} · {row.name}"

        camera_apply_settings_publisher.publish(
            {**settings, "request_id": request_id, "context": context}
        )

        if self.ack_time_s <= 0:
            return

        reply = json.loads(
            ctx.wait_for(
                DEVICE_VIEWER_CAMERA_SETTINGS_APPLIED,
                timeout=self.ack_time_s,
                predicate=lambda message: (
                    json.loads(message).get("request_id") == request_id
                ),
            )
        )

        if not reply.get("ok"):
            logger.warning(
                f"{context}: camera settings not applied: {reply.get('error')}"
            )

        for text in reply.get("warnings", []):
            logger.warning(f"{context}: {text}")

    def _wait_out_lead(self, lead_ms, ctx):
        """Sleep until the camera has been on for lead_ms (stop-aware)."""
        camera_on_at = ctx.protocol.scratch.pop(CAMERA_ON_AT_SCRATCH_KEY, None)

        if lead_ms <= 0 or camera_on_at is None:
            return

        elapsed = time.monotonic() - camera_on_at

        ctx.protocol.sleep(max(0.0, lead_ms / 1000 - elapsed))

    def _fire_capture(self, row, ctx):
        """Publish the legacy-compatible payload and wait for its ack.

        `ctx` is the StepContext — wait_for lives there.
        """
        request_id = uuid.uuid4().hex
        payload = {
            "directory": ctx.protocol.scratch.get(EXPERIMENT_DIR_SCRATCH_KEY, ""),
            "step_description": row.name,
            "step_id": row.dotted_path(),
            "show_status_message": False,
            "request_id": request_id,
        }

        publish_message(
            topic=DEVICE_VIEWER_SCREEN_CAPTURE,
            message=json.dumps(payload),
        )

        if self.ack_time_s <= 0:
            return

        ctx.wait_for(
            DEVICE_VIEWER_MEDIA_CAPTURED,
            timeout=self.ack_time_s,
            predicate=lambda message: (
                json.loads(message).get("request_id") == request_id
            ),
        )


def make_capture_column():
    """Return a fresh Capture compound column (capture, capture_at,
    capture_lead_ms, capture_camera_settings)."""
    return CompoundColumn(
        model=CaptureCompoundModel(),
        view=DictCompoundColumnView(
            cell_views={
                "capture": CheckboxColumnView(),
                "capture_at": CaptureAtComboBoxView(),
                "capture_lead_ms": CaptureLeadSpinBoxView(),
                CAPTURE_CAMERA_SETTINGS_FIELD_ID: CaptureCameraSettingsView(),
            }
        ),
        handler=CaptureHandler(),
    )

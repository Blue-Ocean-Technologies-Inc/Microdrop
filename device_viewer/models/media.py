# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json
from enum import Enum

# Third-party imports.
from pydantic import BaseModel, Field, FilePath, StrictBool

# Enthought library imports.
from traits.api import Bool, Event, HasTraits, Str, observe

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Logger import.
from logger.logger_service import get_logger

app_globals = get_microdrop_redis_globals_manager()
logger = get_logger(__name__)


class MediaType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    OTHER = "other"

    @classmethod
    def get_media_types(self) -> list[str]:
        return [self.VIDEO, self.IMAGE, self.OTHER]


class MediaCaptureMessageModel(BaseModel):
    path: FilePath  # Validates input points to an existing path
    type: MediaType  # Restricted to the Enum values above
    #: Echo of the capture request's request_id (a DEVICE_VIEWER_SCREEN_CAPTURE
    #: capture_data key), so a requester can match the saved file to its own
    #: request; empty for button captures.
    request_id: str = ""


class CameraControlsRequest(BaseModel):
    """Set the active camera's exposure and focus; None means auto."""

    request_id: str = ""
    #: Manual exposure time; None = auto exposure.
    exposure_ms: float | None = Field(default=None, gt=0)
    #: QCamera focus distance, 0.0 (near) to 1.0 (far); None = continuous
    #: auto focus.
    focus_distance: float | None = Field(default=None, ge=0.0, le=1.0)


class CameraControlsApplied(BaseModel):
    """The camera's readback after a CameraControlsRequest, echoing its
    request_id; ok=False carries why (no active camera, unsupported mode)."""

    request_id: str = ""
    ok: bool
    exposure_ms: float | None = None
    focus_distance: float | None = None
    error: str = ""


class RecordingActiveState(BaseModel):
    """
    Validates requests to set recording active state.

    Expects a bool arg.
    """

    state: StrictBool


class RecordingStatePublisher(ValidatedTopicPublisher):
    validator_class = RecordingActiveState

    def publish(self, state: bool):
        """
        Constrict payload for publisher to set recording active state.
        (Validated as StrictBool by RecordingActiveState on publish.)
        """
        super().publish({"state": state})


class MediaCaptureEventModel(HasTraits):
    """In-process notification that a capture file finished writing.

    Lives as a singleton in device_viewer.consts (like
    recording_state_model) so any frontend plugin can observe it instead
    of polling the captures folder; the event's payload is the saved
    file's path. Fired AFTER the file is on disk.
    """

    captured = Event(Str)


class RecordingStateModel(HasTraits):
    """Holds the live video-recording state and mirrors it to app_globals.

    The camera widget sets ``recording`` whenever a recording starts/stops;
    the observer writes it to app_globals so any plugin can read the state
    synchronously instead of subscribing to DEVICE_VIEWER_RECORDING_STATE.
    """

    recording = Bool(False)
    # Set at construction to the canonical key (device_viewer.consts
    # DEVICE_VIEWER_RECORDING_ACTIVE_KEY) — kept defaultless here so that
    # constant stays the single source of truth (consts imports this module,
    # so it can't be imported back without a cycle).
    globals_key = Str()

    @observe("recording")
    def _mirror_recording_state_to_app_globals(self, event):
        if not self.globals_key:
            return
        app_globals[self.globals_key] = event.new
        logger.info(f"App Globals Update: {self.globals_key}: {event.new}")


if __name__ == "__main__":
    from pathlib import Path

    from pydantic import ValidationError

    media = MediaCaptureMessageModel(path=Path(__file__), type=MediaType.VIDEO)

    print(media.model_dump_json())

    try:
        media = MediaCaptureMessageModel(
            path=Path(__file__).with_suffix(".json"), type=MediaType.VIDEO
        )
    except ValidationError as e:
        print(e)
        # Path validation error: file not found

    try:
        media = MediaCaptureMessageModel(
            path=Path(__file__).with_suffix(".json"), type="picture"
        )
    except ValidationError as e:
        print(e)
        # MediaType validation error: invalid type

    rec_pub_model = RecordingStatePublisher()
    rec_pub_model.publish(state=True)

    rec_valid_model = RecordingActiveState.model_validate_json(
        json.dumps({"state": True})
    )

    print(rec_valid_model.state)

import json

from pydantic import BaseModel, FilePath, StrictBool
from enum import Enum
from traits.api import HasTraits, Bool, observe

from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher


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


class RecordingActiveState(BaseModel):
    """
    Validates requests to set recording active state.

    Expects a bool arg.
    """
    state: StrictBool

class RecordingStatePublisher(ValidatedTopicPublisher):
    validator_class = RecordingActiveState

    def publish(self, state: StrictBool):
        """
        Constrict payload for publisher to set recording active state.
        """
        super().publish({"state": state})


class RecordingStateModel(HasTraits):
    """Holds the live video-recording state and mirrors it to app_globals.

    The camera widget sets ``recording`` whenever a recording starts/stops;
    the observer writes it to app_globals so any plugin can read the state
    synchronously instead of subscribing to DEVICE_VIEWER_RECORDING_STATE.
    """

    recording = Bool(False)

    @observe("recording")
    def _mirror_recording_state_to_app_globals(self, event):
        # Lazy imports: device_viewer.consts imports this module (so importing
        # the key at module load would be circular), and acquiring the redis
        # globals manager at import time would force a broker before this
        # widely-imported module is even constructed.
        from device_viewer.consts import DEVICE_VIEWER_RECORDING_ACTIVE_KEY
        from microdrop_application.helpers import get_microdrop_redis_globals_manager
        get_microdrop_redis_globals_manager()[DEVICE_VIEWER_RECORDING_ACTIVE_KEY] = event.new


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
        # Path does not point to a file [type=path_not_file, input_value=WindowsPath('C:/Users/Inf...dia_capture_model.json'), input_type=WindowsPath]

    try:
        media = MediaCaptureMessageModel(path=Path(__file__).with_suffix(".json"), type="picture")
    except ValidationError as e:
        print(e)
        # Input should be 'video', 'image' or 'other' [type=enum, input_value='picture', input_type=str]

    rec_pub_model = RecordingStatePublisher()
    rec_pub_model.publish(state=True)

    rec_valid_model = RecordingActiveState.model_validate_json(json.dumps({"state": True}))

    print(rec_valid_model.state)
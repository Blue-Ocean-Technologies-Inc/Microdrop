from pydantic import BaseModel, FilePath
from enum import Enum


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

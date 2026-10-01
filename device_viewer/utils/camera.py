# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Re-export shim: the camera helpers were split into ``capture``,
``qt_geometry_serialization`` and the ``recording`` package (#642).
Existing importers keep working; migrate them as they are touched."""

# Local imports.
from .capture import ImageSaver, SaveSignals, get_transformed_frame, media_filename
from .qt_geometry_serialization import (
    qpointf_list_deserialize,
    qpointf_list_serialize,
    qtransform_deserialize,
    qtransform_serialize,
)
from .recording.base import VideoRecorderBase, write_transform_sidecar
from .recording.ffmpeg import (
    QT_TO_FFMPEG_PIXEL_FORMATS,
    RAW_RECORDER_QUEUE_MAX_FRAMES,
    RawFFMPEGVideoRecorder,
)
from .recording.native import (
    QT_MEDIA_FILE_FORMATS,
    NativeVideoRecorder,
    qt_video_codec_from_name,
    supported_qt_video_codec_names,
)

__all__ = [
    "ImageSaver",
    "NativeVideoRecorder",
    "QT_MEDIA_FILE_FORMATS",
    "QT_TO_FFMPEG_PIXEL_FORMATS",
    "RAW_RECORDER_QUEUE_MAX_FRAMES",
    "RawFFMPEGVideoRecorder",
    "SaveSignals",
    "VideoRecorderBase",
    "get_transformed_frame",
    "media_filename",
    "qpointf_list_deserialize",
    "qpointf_list_serialize",
    "qt_video_codec_from_name",
    "qtransform_deserialize",
    "qtransform_serialize",
    "supported_qt_video_codec_names",
    "write_transform_sidecar",
]

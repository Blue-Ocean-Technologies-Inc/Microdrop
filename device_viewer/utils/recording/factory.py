# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Build the video recorder the camera preferences select."""

# Local imports.
from ...consts import RECORDER_BACKEND_FFMPEG
from .ffmpeg import RawFFMPEGVideoRecorder
from .native import NativeVideoRecorder

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def build_recorder(
    preferences, session, frame_sink, video_item, resolution=None, fps=None
):
    """Recorder configured from the camera preferences. Both recorders
    share VideoRecorderBase, so callers are agnostic.

    ``session`` is the QMediaCaptureSession the Qt recorder attaches to;
    ``frame_sink`` the session's own full-rate QVideoSink the FFmpeg
    recorder taps. ``resolution``/``fps`` (known at recording start) select
    which per-resolution-class bitrate preference applies to the Qt/MKV
    recorder; before that they are unknown and the bitrate stays
    encoder-chosen.
    """

    if preferences.recorder_backend == RECORDER_BACKEND_FFMPEG:
        # Raw camera planes piped to an ffmpeg subprocess at full camera
        # rate (untouched by the preview frame cap thanks to frame_sink).
        logger.info(
            f"Recorder from preferences: FFmpeg process — "
            f"container={preferences.ffmpeg_container}, "
            f"codec={preferences.ffmpeg_video_codec}, "
            f"preset={preferences.ffmpeg_preset}, "
            f"crf={preferences.ffmpeg_crf}, "
            f"extra args={preferences.ffmpeg_extra_output_args!r}"
        )

        return RawFFMPEGVideoRecorder(
            video_item,
            frame_sink=frame_sink,
            video_codec=preferences.ffmpeg_video_codec,
            preset=preferences.ffmpeg_preset,
            crf=preferences.ffmpeg_crf,
            extra_output_args=preferences.ffmpeg_extra_output_args,
        )

    # Qt's own QMediaRecorder: hardware-encoded, zero per-frame Python work.
    video_bitrate = preferences.recording_bitrate_bps(resolution, fps)
    bitrate_description = (
        f"{video_bitrate:,} bps" if video_bitrate else "encoder default"
    )
    logger.info(
        f"Recorder from preferences: Qt MediaRecorder — "
        f"format={preferences.qt_video_format}, "
        f"codec={preferences.qt_video_codec}, "
        f"bitrate={bitrate_description}"
    )

    return NativeVideoRecorder(
        session=session,
        video_item=video_item,
        file_format=preferences.qt_video_format,
        video_codec=preferences.qt_video_codec,
        video_bitrate=video_bitrate,
    )

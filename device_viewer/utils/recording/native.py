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
from typing import List

# Enthought library imports.
from pyface.qt.QtCore import QSize, QUrl
from pyface.qt.QtMultimedia import QMediaFormat, QMediaRecorder
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem

# Microdrop package imports.
from device_viewer.consts import QT_RECORDER_FORMAT_MKV, QT_RECORDER_FORMAT_MP4

# Local imports.
from .base import VideoRecorderBase

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Preference token -> QMediaFormat container (see NativeVideoRecorder).
QT_MEDIA_FILE_FORMATS = {
    QT_RECORDER_FORMAT_MP4: QMediaFormat.FileFormat.MPEG4,
    QT_RECORDER_FORMAT_MKV: QMediaFormat.FileFormat.Matroska,
}


def supported_qt_video_codec_names(file_format_token) -> List[str]:
    """Names of the video codecs the platform backend can ENCODE into the
    given container (QT_RECORDER_FORMAT_* token). Must run with the
    application up — the backend reports a reduced set headless."""
    media_format = QMediaFormat(QT_MEDIA_FILE_FORMATS[file_format_token])
    return [
        QMediaFormat.videoCodecName(codec)
        for codec in media_format.supportedVideoCodecs(
            QMediaFormat.ConversionMode.Encode
        )
    ]


def qt_video_codec_from_name(name: str):
    """QMediaFormat.VideoCodec whose display name matches, else None."""
    for codec in QMediaFormat.VideoCodec:
        if QMediaFormat.videoCodecName(codec) == name:
            return codec
    return None


class NativeVideoRecorder(VideoRecorderBase):
    """Records the RAW camera stream through Qt's own QMediaRecorder —
    the platform's hardware-accelerated encoding pipeline (Media
    Foundation on Windows). Per-frame cost to the application: zero — no
    frames pass through Python at all, so the GUI stays smooth while
    recording at any resolution.

    The device-alignment perspective warp is NOT baked into the file
    (baking it would force every frame through the GUI thread). Instead
    the video item's alignment geometry is written to a
    ``<video>.transform.json`` sidecar next to the recording, so the
    aligned view can be reproduced offline on demand (same parameters
    ``get_transformed_frame`` consumes per frame).

    Public surface: see VideoRecorderBase.
    """

    def __init__(
        self,
        session,
        video_item: "QGraphicsVideoItem",
        file_format=None,
        video_codec=None,
        video_bitrate=None,
        parent=None,
    ):
        """``file_format`` is a QT_RECORDER_FORMAT_* token (None lets the
        backend infer the container from the output file's extension).
        ``video_codec`` is a QMediaFormat codec display name (see
        supported_qt_video_codec_names); unknown/None falls back to H.264.
        ``video_bitrate`` is bits/s; None records in constant-quality mode
        instead (the encoder picks the rate)."""
        super().__init__(video_item, parent)
        self._was_recording = False

        self._recorder = QMediaRecorder(self)

        session.setRecorder(self._recorder)
        if file_format is not None:
            media_format = QMediaFormat(QT_MEDIA_FILE_FORMATS[file_format])
            codec = qt_video_codec_from_name(video_codec) if video_codec else None
            if codec is None:
                codec = QMediaFormat.VideoCodec.H264
                if video_codec:
                    logger.warning(
                        f"Unknown video codec {video_codec!r}; falling back to H.264"
                    )
            media_format.setVideoCodec(codec)
            self._recorder.setMediaFormat(media_format)
        if video_bitrate:
            # setVideoBitRate is IGNORED in the default constant-quality
            # encoding mode — the bitrate only applies in a bitrate mode.
            self._recorder.setEncodingMode(
                QMediaRecorder.EncodingMode.AverageBitRateEncoding
            )
            self._recorder.setVideoBitRate(video_bitrate)
        else:
            # Pin quality-driven encoding explicitly (the quality level is
            # IGNORED in the bitrate-driven modes) at the top tier — the
            # FFmpeg backend maps this to a low-CRF, visually near-lossless
            # encode — so a backend default change can't silently demote
            # recordings.
            self._recorder.setEncodingMode(
                QMediaRecorder.EncodingMode.ConstantQualityEncoding
            )
            self._recorder.setQuality(QMediaRecorder.Quality.VeryHighQuality)
        self._recorder.errorOccurred.connect(self._on_recorder_error)
        self._recorder.recorderStateChanged.connect(self._on_recorder_state_changed)

    @property
    def is_recording(self) -> bool:
        return (
            self._recorder.recorderState()
            == QMediaRecorder.RecorderState.RecordingState
        )

    def start(self, output_path, resolution, fps):
        """Start recording the RAW camera stream. ``resolution`` is the
        selected camera format's size — pinned on the recorder so the
        output is guaranteed full resolution (e.g. a 1920x1080 format
        records a 1920x1080 file); the backend already records the active
        format by default, this makes it explicit. ``fps`` is left to the
        camera's real delivery rate."""
        if self.is_recording:
            return
        if resolution:
            self._recorder.setVideoResolution(
                QSize(*[int(side) for side in resolution])
            )
        self._recorder.setOutputLocation(QUrl.fromLocalFile(str(output_path)))
        self._recorder.setVideoFrameRate(fps)
        self._recorder.record()
        # Read the settings back FROM the recorder — this is the
        # confirmation that the preference-driven configuration stuck.
        applied_format = self._recorder.mediaFormat()
        logger.info(
            f"Native recording requested: {output_path} at {resolution}; "
            f"applied settings: "
            f"container={applied_format.fileFormat().name}, "
            f"codec={QMediaFormat.videoCodecName(applied_format.videoCodec())}, "
            f"encoding mode={self._recorder.encodingMode().name}, "
            f"video bitrate={self._recorder.videoBitRate():,} bps, "
            f"quality={self._recorder.quality().name}"
        )

    def stop(self):
        """Stop recording; recording_stopped fires on the state change."""
        if self.is_recording:
            logger.info("Stopping native recording...")
            self._recorder.stop()

    def _on_recorder_state_changed(self, state):
        if state == QMediaRecorder.RecorderState.RecordingState:
            self._was_recording = True
            self.recording_started.emit(self._recorder.actualLocation().toLocalFile())
        elif state == QMediaRecorder.RecorderState.StoppedState and self._was_recording:
            self._was_recording = False
            path = self._recorder.actualLocation().toLocalFile()
            self._finalize_recording(path)
            logger.info(f"Native recording stopped: {path}")

    def _on_recorder_error(self, _error, error_string):
        logger.error(f"Native recorder error: {error_string}")
        self.error_occurred.emit(error_string)

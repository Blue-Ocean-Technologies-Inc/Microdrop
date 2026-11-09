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
import queue
import shlex
import shutil
import subprocess
import tempfile
import threading

# Third-party imports.
import numpy as np

# Enthought library imports.
from pyface.qt.QtCore import Slot
from pyface.qt.QtMultimedia import QVideoFrame, QVideoFrameFormat
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem

# Microdrop package imports.
from device_viewer.consts import FFMPEG_DEFAULT_CRF, FFMPEG_PRESETS, FFMPEG_VIDEO_CODECS

# Local imports.
from .base import VideoRecorderBase

# Logger import.
from logger.logger_service import debug_throttled, get_logger

logger = get_logger(__name__)

#: Bound on frames buffered between the GUI thread and the raw recorder's
#: ffmpeg encoder (~2 s at 30 fps); when the encoder falls behind, new
#: frames are dropped so the GUI thread never stalls.
RAW_RECORDER_QUEUE_MAX_FRAMES = 60


#: QVideoFrameFormat.PixelFormat -> ffmpeg rawvideo pix_fmt for the camera
#: formats the raw recorder can pipe WITHOUT a color conversion (a plain
#: plane memcpy). ffmpeg converts to the encoder's format internally (in C).
QT_TO_FFMPEG_PIXEL_FORMATS = {
    QVideoFrameFormat.PixelFormat.Format_NV12: "nv12",
    QVideoFrameFormat.PixelFormat.Format_NV21: "nv21",
    QVideoFrameFormat.PixelFormat.Format_YUV420P: "yuv420p",
    QVideoFrameFormat.PixelFormat.Format_YUV422P: "yuv422p",
    QVideoFrameFormat.PixelFormat.Format_YUYV: "yuyv422",
    QVideoFrameFormat.PixelFormat.Format_UYVY: "uyvy422",
    QVideoFrameFormat.PixelFormat.Format_RGBA8888: "rgba",
    QVideoFrameFormat.PixelFormat.Format_RGBX8888: "rgba",
    QVideoFrameFormat.PixelFormat.Format_BGRA8888: "bgra",
    QVideoFrameFormat.PixelFormat.Format_BGRX8888: "bgra",
    QVideoFrameFormat.PixelFormat.Format_ARGB8888: "argb",
    QVideoFrameFormat.PixelFormat.Format_XRGB8888: "argb",
    QVideoFrameFormat.PixelFormat.Format_ABGR8888: "abgr",
    QVideoFrameFormat.PixelFormat.Format_XBGR8888: "abgr",
}


def _plane_layout(pix_fmt, width, height):
    """[(tight_row_bytes, rows)] per plane for an ffmpeg rawvideo stream —
    used to strip Qt's per-row stride padding while copying."""
    if pix_fmt in ("rgba", "bgra", "argb", "abgr"):
        return [(width * 4, height)]
    if pix_fmt in ("yuyv422", "uyvy422"):
        return [(width * 2, height)]
    if pix_fmt in ("nv12", "nv21"):
        return [(width, height), (width, height // 2)]
    if pix_fmt == "yuv420p":
        return [(width, height), (width // 2, height // 2), (width // 2, height // 2)]
    if pix_fmt == "yuv422p":
        return [(width, height), (width // 2, height), (width // 2, height)]
    raise ValueError(f"Unhandled pixel format {pix_fmt}")


class RawFFMPEGVideoRecorder(VideoRecorderBase):
    """Records the RAW camera frames to H.264 via an ffmpeg subprocess,
    with NO device-alignment perspective warp AND without a per-frame color
    conversion.

    Each frame is mapped and its NATIVE pixel planes are copied ONCE into a
    payload buffer that goes straight to ffmpeg (a memcpy — no conversion),
    in the camera's own pixel format; ffmpeg converts to the encoder's
    format internally (in C). The file is the untransformed camera image at
    its native resolution, and the GUI-thread cost per frame is just that
    single plane copy — no ``frame.toImage()`` (which would force a full
    RGBA color conversion). The alignment geometry is written to a
    ``<video>.transform.json`` sidecar so the aligned view can be
    reproduced offline.

    Frames are handed to a background IO thread that writes to ffmpeg's
    stdin; the queue drops frames when the encoder falls behind so the GUI
    thread never stalls. ffmpeg's stderr goes to a temp file (never a pipe
    nobody drains — a full pipe would block the encoder). The ffmpeg
    pipeline starts lazily on the first frame, because the pixel format and
    size aren't known until then.

    Public surface: see VideoRecorderBase.
    """

    def __init__(
        self,
        video_item: "QGraphicsVideoItem",
        ffmpeg_binary="ffmpeg",
        parent=None,
        frame_sink=None,
        video_codec=FFMPEG_VIDEO_CODECS[0],
        preset=FFMPEG_PRESETS[0],
        crf=FFMPEG_DEFAULT_CRF,
        extra_output_args="",
    ):
        super().__init__(video_item, parent)
        self.ffmpeg_binary = ffmpeg_binary
        self.video_codec = video_codec
        self.preset = preset
        self.crf = crf
        # Advanced escape hatch: extra ffmpeg output options, shell-style
        # (split with shlex and appended before the output path).
        self.extra_output_args = extra_output_args

        self._recording_active = False
        self._output_path = None
        # Frames come from this sink; geometry still comes from the video
        # item. Passing the capture session's own sink keeps recordings at
        # full camera rate while the DISPLAY item receives rate-capped
        # preview frames (see QtCameraDevice.forward_preview_frame).
        self._frame_sink = (
            frame_sink if frame_sink is not None else video_item.videoSink()
        )

        self._process = None
        self._stderr_file = None
        self._io_thread = None
        self._queue = queue.Queue(maxsize=RAW_RECORDER_QUEUE_MAX_FRAMES)
        self._layout = None
        self._frame_payload_bytes = 0
        self._fps = 30.0

    @property
    def is_recording(self) -> bool:
        return self._recording_active

    def _stop_ffmpeg(self):
        """Cleanly close ffmpeg: drain the IO thread, EOF stdin, wait."""
        if self._io_thread:
            self._io_thread.join()
            self._io_thread = None
        if self._process:
            if self._process.stdin:
                try:
                    self._process.stdin.close()
                except OSError as e:
                    logger.debug(f"Raw recorder stdin close: {e}")
            self._process.wait()
            if self._process.returncode != 0 and self._stderr_file:
                self._stderr_file.seek(0)
                logger.error(
                    f"FFmpeg Error: "
                    f"{self._stderr_file.read().decode('utf-8', errors='ignore')}"
                )
        if self._stderr_file:
            self._stderr_file.close()
            self._stderr_file = None
        self._process = None
        self._queue = queue.Queue(maxsize=RAW_RECORDER_QUEUE_MAX_FRAMES)

    def start(self, output_path, resolution, fps):
        if self.is_recording:
            return None
        if not shutil.which(self.ffmpeg_binary):
            self.error_occurred.emit("FFmpeg binary not found.")
            return None

        self._output_path = output_path
        self._fps = float(fps) if fps else 30.0
        # Deferred until the first frame reveals the pixel format/size.
        self._process = None
        self._layout = None
        self._queue = queue.Queue(maxsize=RAW_RECORDER_QUEUE_MAX_FRAMES)

        self._recording_active = True
        self._frame_sink.videoFrameChanged.connect(self._on_frame_arrived)

        self.recording_started.emit(output_path)
        logger.info(f"Raw recording started: {output_path}")
        return True

    @Slot(QVideoFrame)
    def _on_frame_arrived(self, frame):
        """GUI thread: memcpy the native pixel planes, queue for ffmpeg."""
        if not self.is_recording or not frame.isValid():
            return

        if self._process is None and not self._start_native_ffmpeg(frame):
            return

        if self._queue.full():
            debug_throttled(
                logger,
                "raw_recorder_queue_full",
                "Raw recorder encoder behind; dropping frame",
            )
            return

        if not frame.map(QVideoFrame.MapMode.ReadOnly):
            return
        try:
            # ONE copy per plane: each plane lands directly in its final
            # position in the payload (no intermediate chunks, no join).
            payload = bytearray(self._frame_payload_bytes)
            payload_np = np.frombuffer(payload, np.uint8)
            offset = 0
            for plane, (row_bytes, rows) in enumerate(self._layout):
                plane_bytes = row_bytes * rows
                bytes_per_line = frame.bytesPerLine(plane)
                plane_data = np.frombuffer(frame.bits(plane), np.uint8)
                if bytes_per_line == row_bytes:
                    payload_np[offset : offset + plane_bytes] = plane_data[:plane_bytes]
                else:
                    # Strip the per-row stride padding while copying.
                    payload_np[offset : offset + plane_bytes].reshape(rows, row_bytes)[
                        :
                    ] = plane_data[: bytes_per_line * rows].reshape(
                        rows, bytes_per_line
                    )[:, :row_bytes]
                offset += plane_bytes
        finally:
            frame.unmap()

        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            debug_throttled(
                logger,
                "raw_recorder_queue_full",
                "Raw recorder encoder behind; dropping frame",
            )

    def _disconnect_frame_sink(self):
        try:
            self._frame_sink.videoFrameChanged.disconnect(self._on_frame_arrived)
        except Exception as e:
            logger.debug(f"Raw recorder frame sink already disconnected: {e}")

    def _start_native_ffmpeg(self, frame) -> bool:
        pixel_format = frame.surfaceFormat().pixelFormat()
        pix_fmt = QT_TO_FFMPEG_PIXEL_FORMATS.get(pixel_format)
        if pix_fmt is None:
            self._recording_active = False
            self._disconnect_frame_sink()
            self.error_occurred.emit(
                f"Raw recording does not support the camera's "
                f"{pixel_format.name} pixel format"
            )
            return False

        width, height = frame.width(), frame.height()
        self._layout = _plane_layout(pix_fmt, width, height)
        self._frame_payload_bytes = sum(
            row_bytes * rows for row_bytes, rows in self._layout
        )
        command = [
            self.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            pix_fmt,
            "-s",
            f"{width}x{height}",
            "-r",
            f"{self._fps}",
            "-i",
            "-",
            "-c:v",
            self.video_codec,
            "-pix_fmt",
            "yuv420p",
            "-preset",
            self.preset,
            "-crf",
            str(self.crf),
            *shlex.split(self.extra_output_args),
            self._output_path,
        ]
        # stderr goes to a temp file, NOT a pipe: nothing drains a pipe
        # while recording, and a full pipe would block the encoder.
        self._stderr_file = tempfile.TemporaryFile()
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._stderr_file,
            )
        except Exception as e:
            self._recording_active = False
            self._stderr_file.close()
            self._stderr_file = None
            self.error_occurred.emit(f"Failed to start ffmpeg: {e}")
            return False
        self._io_thread = threading.Thread(
            target=self._io_writer, daemon=True, name="raw-recorder-io"
        )
        self._io_thread.start()
        logger.info(
            f"Raw pipeline: {width}x{height} {pix_fmt} "
            f"@ {self._fps} fps -> {self.video_codec} "
            f"(preset {self.preset}, crf {self.crf}"
            + (
                f", extra args {self.extra_output_args!r}"
                if self.extra_output_args
                else ""
            )
            + ")"
        )
        return True

    def _io_writer(self):
        """Write raw plane bytes straight to ffmpeg stdin. A None payload
        is the stop sentinel: everything queued before it gets written."""
        while self._process and self._process.poll() is None:
            try:
                payload = self._queue.get(timeout=0.1)
            except queue.Empty:
                if not self.is_recording and self._queue.empty():
                    break
                continue
            if payload is None:
                break
            try:
                self._process.stdin.write(payload)
            except (BrokenPipeError, ValueError, OSError):
                logger.info("Raw recorder ffmpeg pipe closed")
                break

    def stop(self):
        if not self.is_recording:
            return

        self._recording_active = False

        if self._frame_sink:
            self._disconnect_frame_sink()

        path = self._output_path
        if self._process is not None:
            try:
                self._queue.put_nowait(None)  # stop sentinel
            except queue.Full:
                pass  # _io_writer falls back to the is_recording check
            self._stop_ffmpeg()
            self._finalize_recording(path)
        else:
            logger.warning("Raw recording stopped with no frames")
            self.recording_stopped.emit("")

        logger.info(f"Raw recording stopped: {path}")
        self._output_path = None

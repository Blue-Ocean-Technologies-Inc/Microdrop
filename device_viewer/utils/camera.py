import json
import shlex
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import List, Tuple
import queue

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, QUrl, Signal, QObject, QRunnable, Slot
from PySide6.QtGui import QImage, QTransform, Qt, QPainter
from PySide6.QtMultimedia import (QMediaFormat, QMediaRecorder, QVideoFrame,
                                  QVideoFrameFormat)
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

from device_viewer.consts import (FFMPEG_DEFAULT_CRF, FFMPEG_PRESETS,
                                  FFMPEG_VIDEO_CODECS,
                                  QT_RECORDER_FORMAT_MKV,
                                  QT_RECORDER_FORMAT_MP4,
                                  RECORDING_TRANSFORM_SIDECAR_SUFFIX)
from device_viewer.models.media import MediaType
from device_viewer.views.camera_control_view.utils import _cache_media_capture
from logger.logger_service import get_logger, debug_throttled
logger = get_logger(__name__)

#: Bound on frames buffered between the GUI thread and the raw recorder's
#: ffmpeg encoder (~2 s at 30 fps); when the encoder falls behind, new
#: frames are dropped so the GUI thread never stalls.
RAW_RECORDER_QUEUE_MAX_FRAMES = 60

def qtransform_serialize(transform: QTransform) -> str:
    return json.dumps([transform.m11(), transform.m12(), transform.m13(),
                        transform.m21(), transform.m22(), transform.m23(),
                        transform.m31(), transform.m32(), transform.m33()])

def qtransform_deserialize(data: str) -> QTransform:
    params = json.loads(data)
    return QTransform(params[0], params[1], params[2],
                      params[3], params[4], params[5],
                      params[6], params[7], params[8])

def qpointf_list_serialize(list_qpointf: List[QPointF]) -> List[Tuple[float, float]]:
    return json.dumps([el.toTuple() for el in list_qpointf])

def qpointf_list_deserialize(data: str) -> List[QPointF]:
    return [QPointF(*coord_tuple) for coord_tuple in json.loads(data)]

def get_transformed_frame(src_image: QImage,
                          src_rect: QRectF, target_rect: QRectF,
                          transform: QTransform,
                          target_resolution: tuple[int, int]):
    tw, th = target_resolution

    # Create the output image at the FINAL resolution immediately
    output_image = QImage(tw, th, QImage.Format_RGBA8888)
    output_image.fill(Qt.black) # Black bars for aspect ratio mismatch

    painter = QPainter(output_image)

    # 1. Enable High-Quality Scaling inside the painter
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # 2. Calculate the scale factor between 'canvas' and 'target resolution'
    scale_x = tw / src_rect.width()
    scale_y = th / src_rect.height()

    # 3. Apply scaling globally so everything drawn fits the target res
    painter.scale(scale_x, scale_y)

    # 4. Same coordinate logic as before
    painter.translate(-src_rect.x(), -src_rect.y())
    painter.setTransform(transform, combine=True)

    # Draw the source (NV12 to RGB conversion happens here automatically)
    painter.drawImage(target_rect, src_image)

    painter.end()
    return output_image


class SaveSignals(QObject):
    # Both signals send the save_path.
    save_complete = Signal(str)
    save_failed = Signal(str)


class ImageSaver(QRunnable):
    """PNG-encode + write ``image`` to ``save_path``; run it on a QThreadPool
    (encoding a full-resolution frame takes long enough to visibly freeze the
    GUI when run inline). Callers must hand over an image they will not paint
    into afterwards (pass ``image.copy()`` if unsure) — QImage is implicitly
    shared, so holding the reference is enough and copying here would put a
    second full-frame memcpy on the caller's (GUI) thread."""

    def __init__(self, image, save_path):
        super().__init__()
        self.image = image
        self.save_path = save_path
        self.signals = SaveSignals()

    def run(self):
        try:
            # 1. Heavy PNG encode + disk I/O happens here.
            if self.image.save(self.save_path, "PNG"):
                logger.info(f"Saved image to: {self.save_path}")
                # 2. Tell the UI we are done (queued back to the GUI thread).
                self.signals.save_complete.emit(self.save_path)
            else:
                logger.error(f"Failed to save image: {self.save_path}")
                self.signals.save_failed.emit(self.save_path)
        except Exception as e:
            logger.error(f"Failed to save image {self.save_path}: {e}")
            self.signals.save_failed.emit(self.save_path)


class VideoRecorderBase(QObject):
    """Common surface of the interchangeable video recorders
    (NativeVideoRecorder, RawFFMPEGVideoRecorder), so call sites can swap
    implementations without touching anything but construction:

    - ``start(output_path, resolution, fps)`` / ``stop()``
    - ``is_recording`` property
    - ``current_image`` (always None — screenshots fall back to the live
      sink)
    - ``recording_started`` / ``recording_stopped`` / ``error_occurred``
      signals

    Subclasses call ``_finalize_recording`` when a recording lands on disk;
    it performs the shared stop-side bookkeeping (alignment-transform
    sidecar, capture cache, ``recording_stopped``).
    """

    recording_started = Signal(str)  # Emits path when started
    recording_stopped = Signal(str)  # Emits output path
    error_occurred = Signal(str)

    def __init__(self, video_item: 'QGraphicsVideoItem', parent=None):
        super().__init__(parent)
        self._video_item = video_item
        self.current_image = None  # screenshots fall back to the live sink

    @property
    def is_recording(self) -> bool:
        raise NotImplementedError

    def start(self, output_path, resolution, fps):
        """Start recording to ``output_path``. ``resolution`` is the
        selected camera format's size; ``fps`` its nominal frame rate."""
        raise NotImplementedError

    def stop(self):
        """Stop recording; ``recording_stopped`` fires once the file is
        finalized."""
        raise NotImplementedError

    def _finalize_recording(self, output_path):
        """Shared stop-side bookkeeping: persist the alignment geometry
        sidecar, cache the capture, announce the recording."""
        write_transform_sidecar(self._video_item, output_path)
        _cache_media_capture.send(MediaType.VIDEO, output_path)
        self.recording_stopped.emit(output_path)


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
    return [QMediaFormat.videoCodecName(codec)
            for codec in media_format.supportedVideoCodecs(
                QMediaFormat.ConversionMode.Encode)]


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

    def __init__(self, session, video_item: 'QGraphicsVideoItem',
                 file_format=None, video_codec=None, video_bitrate=None,
                 parent=None):
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
            codec = (qt_video_codec_from_name(video_codec)
                     if video_codec else None)
            if codec is None:
                codec = QMediaFormat.VideoCodec.H264
                if video_codec:
                    logger.warning(f"Unknown video codec {video_codec!r}; "
                                   f"falling back to H.264")
            media_format.setVideoCodec(codec)
            self._recorder.setMediaFormat(media_format)
        if video_bitrate:
            # setVideoBitRate is IGNORED in the default constant-quality
            # encoding mode — the bitrate only applies in a bitrate mode.
            self._recorder.setEncodingMode(
                QMediaRecorder.EncodingMode.AverageBitRateEncoding)
            self._recorder.setVideoBitRate(video_bitrate)
        else:
            # Pin quality-driven encoding explicitly (the quality level is
            # IGNORED in the bitrate-driven modes) at the top tier — the
            # FFmpeg backend maps this to a low-CRF, visually near-lossless
            # encode — so a backend default change can't silently demote
            # recordings.
            self._recorder.setEncodingMode(
                QMediaRecorder.EncodingMode.ConstantQualityEncoding)
            self._recorder.setQuality(QMediaRecorder.Quality.VeryHighQuality)
        self._recorder.errorOccurred.connect(self._on_recorder_error)
        self._recorder.recorderStateChanged.connect(self._on_recorder_state_changed)

    @property
    def is_recording(self) -> bool:
        return (self._recorder.recorderState()
                == QMediaRecorder.RecorderState.RecordingState)

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
            self._recorder.setVideoResolution(QSize(*[int(side)
                                                      for side in resolution]))
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
            f"quality={self._recorder.quality().name}")

    def stop(self):
        """Stop recording; recording_stopped fires on the state change."""
        if self.is_recording:
            logger.info("Stopping native recording...")
            self._recorder.stop()

    def _on_recorder_state_changed(self, state):
        if state == QMediaRecorder.RecorderState.RecordingState:
            self._was_recording = True
            self.recording_started.emit(
                self._recorder.actualLocation().toLocalFile())
        elif (state == QMediaRecorder.RecorderState.StoppedState
                and self._was_recording):
            self._was_recording = False
            path = self._recorder.actualLocation().toLocalFile()
            self._finalize_recording(path)
            logger.info(f"Native recording stopped: {path}")

    def _on_recorder_error(self, _error, error_string):
        logger.error(f"Native recorder error: {error_string}")
        self.error_occurred.emit(error_string)


def write_transform_sidecar(video_item, video_path):
    """Persist the alignment geometry needed to reproduce the
    device-aligned (warped) view offline — the same parameters the
    legacy pipeline fed to get_transformed_frame for every frame."""
    sidecar = {
        "transform": json.loads(
            qtransform_serialize(video_item.transform())),
        "scene_bounding_rect": list(
            video_item.sceneBoundingRect().getRect()),
        "bounding_rect": list(video_item.boundingRect().getRect()),
    }
    sidecar_path = Path(video_path).with_suffix(
        RECORDING_TRANSFORM_SIDECAR_SUFFIX)
    try:
        sidecar_path.write_text(json.dumps(sidecar, indent=2))
        logger.info(f"Wrote recording transform sidecar: {sidecar_path}")
    except Exception as e:
        logger.warning(f"Could not write transform sidecar: {e}")


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
        return [(width, height),
                (width // 2, height // 2), (width // 2, height // 2)]
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

    def __init__(self, video_item: 'QGraphicsVideoItem', ffmpeg_binary="ffmpeg",
                 parent=None, frame_sink=None,
                 video_codec=FFMPEG_VIDEO_CODECS[0],
                 preset=FFMPEG_PRESETS[0],
                 crf=FFMPEG_DEFAULT_CRF,
                 extra_output_args=""):
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
        # preview frames (see CameraControlWidget._forward_preview_frame).
        self._frame_sink = (frame_sink if frame_sink is not None
                            else video_item.videoSink())

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
                logger.error(f"FFmpeg Error: "
                             f"{self._stderr_file.read().decode('utf-8', errors='ignore')}")
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
            debug_throttled(logger, "raw_recorder_queue_full",
                            "Raw recorder encoder behind; dropping frame")
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
                    payload_np[offset:offset + plane_bytes] = \
                        plane_data[:plane_bytes]
                else:
                    # Strip the per-row stride padding while copying.
                    payload_np[offset:offset + plane_bytes].reshape(
                        rows, row_bytes)[:] = (
                        plane_data[:bytes_per_line * rows]
                        .reshape(rows, bytes_per_line)[:, :row_bytes])
                offset += plane_bytes
        finally:
            frame.unmap()

        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            debug_throttled(logger, "raw_recorder_queue_full",
                            "Raw recorder encoder behind; dropping frame")

    def _disconnect_frame_sink(self):
        try:
            self._frame_sink.videoFrameChanged.disconnect(
                self._on_frame_arrived)
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
                f"{pixel_format.name} pixel format")
            return False

        width, height = frame.width(), frame.height()
        self._layout = _plane_layout(pix_fmt, width, height)
        self._frame_payload_bytes = sum(
            row_bytes * rows for row_bytes, rows in self._layout)
        command = [
            self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", pix_fmt,
            "-s", f"{width}x{height}", "-r", f"{self._fps}", "-i", "-",
            "-c:v", self.video_codec, "-pix_fmt", "yuv420p",
            "-preset", self.preset, "-crf", str(self.crf),
            *shlex.split(self.extra_output_args),
            self._output_path,
        ]
        # stderr goes to a temp file, NOT a pipe: nothing drains a pipe
        # while recording, and a full pipe would block the encoder.
        self._stderr_file = tempfile.TemporaryFile()
        try:
            self._process = subprocess.Popen(
                command, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=self._stderr_file)
        except Exception as e:
            self._recording_active = False
            self._stderr_file.close()
            self._stderr_file = None
            self.error_occurred.emit(f"Failed to start ffmpeg: {e}")
            return False
        self._io_thread = threading.Thread(target=self._io_writer,
                                           daemon=True,
                                           name="raw-recorder-io")
        self._io_thread.start()
        logger.info(f"Raw pipeline: {width}x{height} {pix_fmt} "
                    f"@ {self._fps} fps -> {self.video_codec} "
                    f"(preset {self.preset}, crf {self.crf}"
                    + (f", extra args {self.extra_output_args!r}"
                       if self.extra_output_args else "") + ")")
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
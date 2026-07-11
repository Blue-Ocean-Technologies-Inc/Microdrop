import json
import shutil
import subprocess
import threading
from pathlib import Path
from typing import List, Tuple
import queue

from PySide6.QtCore import QPointF, QRectF, QSize, QUrl, Signal, QObject, QRunnable, Slot, QThread
from PySide6.QtGui import QImage, QTransform, Qt, QPainter
from PySide6.QtMultimedia import QMediaFormat, QMediaRecorder, QVideoFrame
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

from device_viewer.consts import RECORDING_TRANSFORM_SIDECAR_SUFFIX
from device_viewer.models.media import MediaType
from device_viewer.views.camera_control_view.utils import _cache_media_capture
from logger.logger_service import get_logger
logger = get_logger(__name__)

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
    # Signal sends the (media_type, save_path)
    save_complete = Signal(str)


class ImageSaver(QRunnable):
    def __init__(self, image, save_path):
        super().__init__()
        # Copy image to ensure it doesn't change while we save
        self.image = image.copy()
        self.save_path = save_path
        self.signals = SaveSignals()

    def run(self):
        try:
            # 1. Heavy I/O happens here
            self.image.save(self.save_path, "PNG")
            logger.info(f"Saved image to: {self.save_path}")

            # 2. Tell the UI we are done
            self.signals.save_complete.emit(self.save_path)

        except Exception as e:
            logger.error(f"Failed to save image: {e}")


class VideoProcessWorker(QObject):
    """
    Internal Worker: Runs on a background QThread.
    Handles heavy image transformations and pushing to the thread-safe queue.
    """
    def __init__(self, write_queue, target_resolution):
        super().__init__()
        self._write_queue = write_queue
        self._resolution = target_resolution
        self._is_running = True

    @Slot(QImage, QRectF, QRectF, QTransform)
    def process_frame(self, src_image, src_rect, target_rect, transform):
        if not self._is_running:
            return

        try:
            # 1. Perform the heavy affine transformations (Cropping/Zooming)
            result_image = get_transformed_frame(
                src_image, src_rect, target_rect, transform, self._resolution
            )

            logger.debug(f"Processed frame: {result_image}")

            # 2. Push to the thread-safe queue for the FFmpeg writer
            if not result_image.isNull():
                logger.debug(f"Pushing frame to ffmpeg queue")
                self._write_queue.put(result_image)
            else:
                logger.warning(f"Got null image. Skipping frame")

        except Exception as e:
            logger.error(f"Video image processing worker Error: {e}")

    def stop(self):
        self._is_running = False
        logger.debug(f"Video image processing worker thread Stopped.")


class NativeVideoRecorder(QObject):
    """Records the RAW camera stream through Qt's own QMediaRecorder —
    the platform's hardware-accelerated encoding pipeline (Media
    Foundation on Windows). Per-frame cost to the application: zero — no
    frames pass through Python at all, so the GUI stays smooth while
    recording at any resolution.

    The device-alignment perspective warp is NOT baked into the file
    (baking it is what forced every frame through the GUI thread — see
    VideoRecorder below). Instead the video item's alignment geometry is
    written to a ``<video>.transform.json`` sidecar next to the
    recording, so the aligned view can be reproduced offline on demand
    (same parameters ``get_transformed_frame`` consumes per frame).

    Drop-in for VideoRecorder's public surface: start/stop, is_recording,
    current_image (always None — screenshots fall back to the live sink),
    and the recording_started/recording_stopped/error_occurred signals.
    """

    recording_started = Signal(str)  # Emits path when started
    recording_stopped = Signal(str)  # Emits output path
    error_occurred = Signal(str)

    def __init__(self, session, video_item: 'QGraphicsVideoItem', parent=None):
        super().__init__(parent)
        self._video_item = video_item
        self.current_image = None  # VideoRecorder parity (see class docstring)
        self._was_recording = False

        self._recorder = QMediaRecorder(self)
        session.setRecorder(self._recorder)
        # Matroska/H.264, matching the legacy ffmpeg-pipe recordings'
        # .mkv container (Qt's FFmpeg multimedia backend muxes it).
        media_format = QMediaFormat(QMediaFormat.FileFormat.Matroska)
        media_format.setVideoCodec(QMediaFormat.VideoCodec.H264)
        self._recorder.setMediaFormat(media_format)
        self._recorder.setQuality(QMediaRecorder.Quality.HighQuality)
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
        self._recorder.record()
        logger.info(f"Native recording requested: {output_path} "
                    f"at {resolution}")

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
            self._write_transform_sidecar(path)
            _cache_media_capture.send(MediaType.VIDEO, path)
            self.recording_stopped.emit(path)
            logger.info(f"Native recording stopped: {path}")

    def _on_recorder_error(self, _error, error_string):
        logger.error(f"Native recorder error: {error_string}")
        self.error_occurred.emit(error_string)

    def _write_transform_sidecar(self, video_path):
        """Persist the alignment geometry needed to reproduce the
        device-aligned (warped) view offline — the same parameters the
        legacy pipeline fed to get_transformed_frame for every frame."""
        sidecar = {
            "transform": json.loads(
                qtransform_serialize(self._video_item.transform())),
            "scene_bounding_rect": list(
                self._video_item.sceneBoundingRect().getRect()),
            "bounding_rect": list(self._video_item.boundingRect().getRect()),
        }
        sidecar_path = Path(video_path).with_suffix(
            RECORDING_TRANSFORM_SIDECAR_SUFFIX)
        try:
            sidecar_path.write_text(json.dumps(sidecar, indent=2))
            logger.info(f"Wrote recording transform sidecar: {sidecar_path}")
        except Exception as e:
            logger.warning(f"Could not write transform sidecar: {e}")


class VideoRecorder(QObject):
    """
    Main Public API.
    Manages FFmpeg process, IO Thread, and Processing QThread.
    """
    recording_started = Signal(str) # Emits path when started
    recording_stopped = Signal(str) # Emits output path
    error_occurred = Signal(str)

    # Internal signal to bridge UI thread and Worker thread
    _send_to_worker = Signal(QImage, QRectF, QRectF, QTransform)

    def __init__(self, video_item: 'QGraphicsVideoItem', ffmpeg_binary="ffmpeg",
                 parent=None, frame_sink=None):
        super().__init__(parent)
        self.ffmpeg_binary = ffmpeg_binary

        # State
        self.is_recording = False
        self._output_path = None
        self._video_item = video_item
        # Frames come from this sink; geometry still comes from the video
        # item. Passing the capture session's own sink keeps recordings at
        # full camera rate while the DISPLAY item receives rate-capped
        # preview frames (see CameraControlWidget._forward_preview_frame).
        self._frame_sink = frame_sink if frame_sink is not None else video_item.videoSink()
        self.current_image = None

        # FFmpeg / IO internals
        self._process = None
        self._io_thread = None
        self._queue = queue.Queue(maxsize=60)

        # QThread Worker internals
        self._worker_thread = None
        self._worker = None

    ######################################################################################################
    # Protected Helper methods
    ######################################################################################################

    def _start_worker_thread(self, resolution):
        """Sets up the QThread for image transformation."""

        logger.debug("Starting video recorder worker thread...")

        self._worker_thread = QThread()
        self._worker = VideoProcessWorker(self._queue, resolution)
        self._worker.moveToThread(self._worker_thread)

        # Connect internal signal to worker slot
        self._send_to_worker.connect(self._worker.process_frame)

        # Cleanup hooks
        self._worker_thread.finished.connect(self._worker.deleteLater)
        self._worker_thread.start()

        logger.debug("Done starting video image processing worker thread.")

    @Slot(QVideoFrame)
    def _on_frame_arrived(self, frame):
        """
        Captured on UI Thread.
        Extracts geometry and image, then emits to Worker Thread immediately.
        """
        if not self.is_recording:
            return

        logger.debug(f"Frame arrived: {frame}")

        # Convert to QImage in UI thread (fast enough usually, and safe)
        # We do this here because QVideoFrame ownership can be tricky across threads
        image = frame.toImage()

        # Capture geometry state NOW (UI thread), as it might change while worker processes
        self._send_to_worker.emit(
            image,
            self._video_item.sceneBoundingRect(),
            self._video_item.boundingRect(),
            self._video_item.transform()
        )

    ## ------------------- FFMPEG Process Management -------------------------------------------

    def _start_ffmpeg(self, path, resolution, fps):
        """Launches the FFmpeg subprocess and the Python IO writer thread."""
        w, h = resolution
        command = [
            self.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{w}x{h}",
            "-pix_fmt",
            "rgba",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-crf",
            "17",
            path,
        ]

        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            logger.debug(f"Done starting FFmpeg subprocess: {command}")

            # Start the IO thread (Python thread, not QThread, for blocking file I/O)
            self._io_thread = threading.Thread(target=self._io_writer, daemon=True)
            self._io_thread.start()

            logger.debug(f"Done starting FFmpeg queue pushing thread.")

            return True

        except Exception as e:
            logger.error(f"Failed to start FFmpeg: {e}")
            self.error_occurred.emit(str(e))
            return False

    def _stop_ffmpeg(self):
        """Cleanly closes FFmpeg."""
        logger.debug("Attempting to stop FFmpeg process...")
        # Wait for IO thread to empty the queue
        if self._io_thread:
            self._io_thread.join()

        # Close stdin to signal EOF to FFmpeg
        if self._process:
            if self._process.stdin:
                self._process.stdin.close()

            self._process.wait()

            if self._process.returncode != 0:
                _, err = self._process.communicate()
                logger.error(
                    f"FFmpeg Error: {err.decode('utf-8', errors='ignore')}"
                )

        # Reset
        self._process = None
        self._queue = queue.Queue(maxsize=60)

        logger.debug(f"FFmpeg process stopped")

    def _io_writer(self):
        """Thread that strictly writes bytes to FFmpeg stdin."""
        while self._process and self._process.poll() is None:
            try:
                # Timeout allows us to check loop condition periodically
                img = self._queue.get(timeout=0.1)

                self._process.stdin.write(img.constBits())
                self.current_image = img

                logger.debug(f"Writing image: {self.current_image}")

            except queue.Empty:

                if not self.is_recording and self._queue.empty():
                    logger.debug("Fffmpeg Queue Empty and not recording anymore.")
                    break

                logger.debug("Fffmpeg Queue Empty")

            except (BrokenPipeError, ValueError):
                logger.info("FFmpeg broken pipe error")
                break

    ############################################################################################
    # Public Main Start and Stop routines
    ############################################################################################

    def start(self, output_path, resolution, fps):
        """
        Starts the recording pipeline.
        :param video_item: The QGraphicsVideoItem to record from.
        """
        if self.is_recording:
            return None

        # 1. Validation
        if not shutil.which(self.ffmpeg_binary):
            self.error_occurred.emit("FFmpeg binary not found.")
            return None

        self._output_path = output_path

        # Handle odd resolutions (FFmpeg libx264 requirement)
        w, h = int(resolution[0]), int(resolution[1])
        w -= 1 if w % 2 != 0 else 0
        h -= 1 if h % 2 != 0 else 0
        final_res = (w, h)

        # 2. Start FFmpeg Process
        if not self._start_ffmpeg(output_path, final_res, fps):
            return None

        # 3. Start Background Processing Thread (QThread)
        self._start_worker_thread(final_res)

        # 4. Connect to Video Source
        # We connect the video sink directly to our internal handler
        self.is_recording = True
        self._frame_sink.videoFrameChanged.connect(self._on_frame_arrived)

        self.recording_started.emit(output_path)
        logger.info(f"Recording started: {output_path}")

        return True

    def stop(self):
        """Stops recording, joins threads, cleans up."""
        if not self.is_recording:
            return

        logger.debug("Attempting to stop recording...")

        self.is_recording = False

        # 1. Disconnect Source (Stop incoming data)
        if self._frame_sink:
            try:
                self._frame_sink.videoFrameChanged.disconnect(self._on_frame_arrived)
            except Exception:
                pass

        # 2. Stop Worker Thread (Image Processing)
        if self._worker:
            self._worker.stop()
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()

        # 3. Stop IO Thread & FFmpeg (Write remaining queue)
        self._stop_ffmpeg()

        ## Save path to cache
        _cache_media_capture.send(MediaType.VIDEO, self._output_path)

        # update UI for any dialogs.
        self.recording_stopped.emit(self._output_path)
        logger.info(f"Recording stopped: {self._output_path}")
        self._output_path = None
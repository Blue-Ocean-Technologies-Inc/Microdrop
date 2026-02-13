import json
import shutil
import subprocess
import threading
from typing import List, Tuple
import queue

from PySide6.QtCore import QPointF, QRectF, Signal, QObject, QRunnable, Slot, QThread
from PySide6.QtGui import QImage, QTransform, Qt, QPainter
from PySide6.QtMultimedia import QVideoFrame
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

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
    save_complete = Signal(str, str)


class ImageSaver(QRunnable):
    def __init__(self, image, save_path, name):
        super().__init__()
        # Copy image to ensure it doesn't change while we save
        self.image = image.copy()
        self.save_path = save_path
        self.name = name
        self.signals = SaveSignals()

    def run(self):
        try:
            # 1. Heavy I/O happens here
            self.image.save(self.save_path, "PNG")
            logger.info(f"Saved image to: {self.save_path}")

            # 2. Tell the UI we are done
            self.signals.save_complete.emit(self.name, self.save_path)

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

    def __init__(self, video_item: 'QGraphicsVideoItem', ffmpeg_binary="ffmpeg", parent=None):
        super().__init__(parent)
        self.ffmpeg_binary = ffmpeg_binary

        # State
        self.is_recording = False
        self._output_path = None
        self._video_item = video_item
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
        self._video_item.videoSink().videoFrameChanged.connect(self._on_frame_arrived)

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
        if self._video_item:
            try:
                self._video_item.videoSink().videoFrameChanged.disconnect(self._on_frame_arrived)
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

        self.recording_stopped.emit(self._output_path)
        logger.info("Recording stopped")
        self._output_path = None

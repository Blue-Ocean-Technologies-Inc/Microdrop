import json
import subprocess
import threading
from typing import List, Tuple
import queue

from PySide6.QtCore import QPointF, QRectF, Signal, QObject, QRunnable
from PySide6.QtGui import QImage, QTransform, Qt, QPainter

from logger.logger_service import get_logger
from microdrop_application.dialogs.pyface_wrapper import success

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


class VideoRecorder:
    def __init__(self, ffmpeg_binary="ffmpeg"):
        self.current_image = None
        self._output_path = None
        self.ffmpeg_binary = ffmpeg_binary
        self._process = None
        self._worker_thread = None
        self._queue = queue.Queue(maxsize=60)
        self._is_recording = False
        self.width = 0
        self.height = 0
        self.resolution = (0,0)

    def start(self, output_path, resolution, fps=30):
        if self._is_recording:
            return False

        self._output_path = output_path

        width, height = resolution

        # Ensure even dimensions (required by libx264)
        self.width = int(width)
        self.height = int(height)
        if self.width % 2 != 0:
            self.width -= 1
        if self.height % 2 != 0:
            self.height -= 1

        self.resolution = (self.width, self.height)

        self._is_recording = True

        # FFmpeg Command for High Quality
        # -crf 17: Visually Lossless (Lower is better, 0 is lossless, 17-18 is sweet spot)
        # -preset ultrafast: Essential for 1080p/4K recording to prevent lag
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
            f"{self.width}x{self.height}",
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
            "17",  # <-- HIGH QUALITY CHANGE
            output_path,
        ]

        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._worker_thread = threading.Thread(
                target=self._process_queue, daemon=True
            )
            self._worker_thread.start()
            logger.info(f"Recording started: {width}x{height} @ {fps}FPS -> CRF 17")
            return True
        except Exception as e:
            logger.error(f"FFmpeg launch failed: {e}")
            self._is_recording = False
            return False

    def write_frame(self, qimage):
        if not self._is_recording or qimage.isNull():
            return

        try:
            self._queue.put(qimage)
            self.current_image = qimage

        except Exception as e:
            logger.error(f"Frame drop: {e}")

    def stop(self):
        if not self._is_recording:
            return
        self._is_recording = False

        if self._worker_thread:
            self._worker_thread.join()

        if self._process:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.wait()
            if self._process.returncode != 0:
                _, err = self._process.communicate()
                logger.error(f"FFmpeg Error: {err.decode('utf-8', errors='ignore')}")
            else:
                logger.info(f"Recording saved successfully to {self._output_path}")

        self._process = None
        self._queue = queue.Queue()

    def _process_queue(self):
        """Heavy I/O and format conversion happens here in a background thread."""
        while self._is_recording or not self._queue.empty():
            try:
                img = self._queue.get(timeout=0.1)

                # Format conversion and bit-extraction happen HERE, not in the UI thread
                if img.format() != QImage.Format_RGBA8888:
                    img = img.convertToFormat(QImage.Format_RGBA8888)

                # Write directly from memory view to pipe
                self._process.stdin.write(img.constBits())

            except (queue.Empty, BrokenPipeError):
                if not self._is_recording:
                    break
                continue


class VideoRecorderWorker(QObject):
    error_occurred = Signal(str)

    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

        self._is_recording = True

    def process_frame(self, src_image, src_rect: QRectF, target_rect: QRectF, transform: QTransform):
        """
        Runs the heavy transformation and writing logic in the background.
        """
        if not self._is_recording:
            return
        try:
            src_image = src_image.toImage()
            result_image = get_transformed_frame(src_image, src_rect, target_rect, transform, target_resolution=self.recorder.resolution)

            # --- 3. Write to FFmpeg (Blocking I/O) ---
            if not result_image.isNull():
                self.recorder.write_frame(result_image)

        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self._is_recording = False


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

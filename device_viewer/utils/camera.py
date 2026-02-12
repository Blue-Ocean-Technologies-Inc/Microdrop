import json
import subprocess
import threading
from typing import List, Tuple
import queue

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QTransform, Qt

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



class VideoRecorder:
    def __init__(self, ffmpeg_binary="ffmpeg"):
        self._output_path = None
        self.ffmpeg_binary = ffmpeg_binary
        self._process = None
        self._worker_thread = None
        self._queue = queue.Queue()
        self._is_recording = False
        self._width = 0
        self._height = 0

    def start(self, output_path, width, height, fps=30):
        if self._is_recording:
            return False

        self._output_path = output_path

        # Ensure even dimensions (required by libx264)
        self._width = int(width)
        self._height = int(height)
        if self._width % 2 != 0:
            self._width -= 1
        if self._height % 2 != 0:
            self._height -= 1

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
            f"{self._width}x{self._height}",
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
        if not self._is_recording:
            return
        try:
            # Check for resolution mismatch (e.g., camera rotated or changed)
            if qimage.width() != self._width or qimage.height() != self._height:
                # Fast scaling (SmoothTransformation is better quality but slower)
                qimage = qimage.scaled(
                    self._width,
                    self._height,
                    Qt.IgnoreAspectRatio,
                    Qt.FastTransformation,
                )

            if qimage.format() != QImage.Format_RGBA8888:
                qimage = qimage.convertToFormat(QImage.Format_RGBA8888)

            raw_data = qimage.constBits().tobytes()
            self._queue.put(raw_data)
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
        while True:
            try:
                data = self._queue.get(timeout=0.5)
            except queue.Empty:
                if not self._is_recording:
                    break
                continue

            if self._process:
                try:
                    self._process.stdin.write(data)
                except:
                    break
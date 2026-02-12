import sys
import logging
from datetime import datetime
from pathlib import Path

# --- PySide6 Imports ---
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QGraphicsView,
    QGraphicsScene,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QLabel,
)
from PySide6.QtMultimedia import (
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
)
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtCore import Qt, QSizeF, Slot
from PySide6.QtGui import QBrush

from device_viewer.utils.camera import VideoRecorder

# --- Logging Setup ---
from logger.logger_service import get_logger, init_logger
logger = get_logger(__name__)

# ==========================================
# 2. Camera Runner (Resolution Aware)
# ==========================================
class CameraRunner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 HD Recorder")
        self.resize(1000, 700)

        self.recorder = VideoRecorder()
        self._output_path = None
        self.is_recording = False
        self.fps = 30

        # UI Setup
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(QBrush(Qt.black))
        layout.addWidget(self.view)

        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)

        self.record_btn = QPushButton("Start HD Recording")
        self.record_btn.clicked.connect(self.toggle_recording)
        self.record_btn.setFixedHeight(50)
        self.record_btn.setStyleSheet(
            "background-color: #2ecc71; color: white; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(self.record_btn)

        self.init_camera()

    def init_camera(self):
        """Finds camera and forces HIGHEST supported resolution."""
        cameras = QMediaDevices.videoInputs()
        if not cameras:
            self.status_label.setText("No Camera Found")
            self.record_btn.setEnabled(False)
            return

        camera_device = cameras[0]
        self.camera = QCamera(camera_device)
        self.capture_session = QMediaCaptureSession()
        self.capture_session.setCamera(self.camera)
        self.capture_session.setVideoOutput(self.video_item)

        # --- RESOLUTION SELECTION LOGIC ---
        # 1. Get all supported formats
        formats = camera_device.videoFormats()
        if formats:
            # 2. Sort by Resolution (Width * Height) Descending
            best_format = max(
                formats,
                key=lambda fmt: fmt.resolution().width() * fmt.resolution().height(),
            )

            # 3. Apply the format to the camera
            self.camera.setCameraFormat(best_format)

            res = best_format.resolution()
            self.cam_width = res.width()
            self.cam_height = res.height()

            # 4. Update Video Item Size to match aspect ratio
            self.video_item.setSize(QSizeF(self.cam_width, self.cam_height))
            # Scale view to fit window without distortion
            self.view.fitInView(self.video_item, Qt.KeepAspectRatio)

            msg = f"Active: {camera_device.description()} @ {self.cam_width}x{self.cam_height}"
        else:
            # Fallback if no formats reported
            self.cam_width = 640
            self.cam_height = 480
            msg = f"Active: {camera_device.description()} (Default Res)"

        self.camera.start()
        self.status_label.setText(msg)

    @Slot()
    def toggle_recording(self):
        if not self.is_recording:
            # --- START ---
            filename = f"hd_rec_{datetime.now().strftime('%H%M%S')}.mp4"
            self._output_path = save_path = str(Path.cwd() / filename)
            # CRITICAL: Use the Camera's ACTUAL resolution, not the UI size
            # This ensures 1:1 pixel mapping
            if self.recorder.start(
                save_path, self.cam_width, self.cam_height, self.fps
            ):
                self.is_recording = True

                # Connect Signal
                self.video_item.videoSink().videoFrameChanged.connect(
                    self.process_frame
                )

                self.record_btn.setText("Stop Recording")
                self.record_btn.setStyleSheet(
                    "background-color: #e74c3c; color: white;"
                )
                self.status_label.setText(
                    f"Recording... {self.cam_width}x{self.cam_height} (High Quality)"
                )
        else:
            # --- STOP ---
            self.is_recording = False
            try:
                self.video_item.videoSink().videoFrameChanged.disconnect(
                    self.process_frame
                )
            except:
                pass

            self.recorder.stop()
            self.record_btn.setText("Start HD Recording")
            self.record_btn.setStyleSheet("background-color: #2ecc71; color: white;")
            self.status_label.setText(f"Saved: {Path(self._output_path).name}")

    @Slot()
    def process_frame(self, frame):
        """Receives native QVideoFrame from sink."""
        if not self.is_recording:
            return

        # .toImage() converts the frame to QImage on the CPU
        # This preserves the full resolution of the source frame
        image = frame.toImage()

        self.recorder.write_frame(image)

    def resizeEvent(self, event):
        # Keep video centered and fitted when window resizes
        if hasattr(self, "video_item"):
            self.view.fitInView(self.video_item, Qt.KeepAspectRatio)
        super().resizeEvent(event)

    def closeEvent(self, event):
        if self.is_recording:
            self.toggle_recording()
        self.camera.stop()
        event.accept()


if __name__ == "__main__":
    init_logger()
    app = QApplication(sys.argv)
    window = CameraRunner()
    window.show()
    sys.exit(app.exec())

import sys
import os

if sys.platform.startswith('linux'):
    os.environ["QT_MEDIA_BACKEND"] = "gstreamer"

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGraphicsView,
    QGraphicsScene,
    QSlider,
    QComboBox,
)
from PySide6.QtMultimedia import (
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
)
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtCore import Qt


class CameraSceneFix(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Responsive Camera Scene")

        self.session = QMediaCaptureSession()
        self.camera = None
        self.available_cameras = []
        self.available_formats = []

        # --- 1. SETUP SCENE & VIEW ---
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)

        # --- 2. SETUP VIDEO ITEM ---
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.session.setVideoOutput(self.video_item)

        # --- UI LAYOUT ---
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Camera:"))
        self.combo_cameras = QComboBox()
        self.combo_cameras.setMinimumWidth(200)
        controls.addWidget(self.combo_cameras)

        controls.addWidget(QLabel("Res:"))
        self.combo_resolutions = QComboBox()
        self.combo_resolutions.setMinimumWidth(250)
        controls.addWidget(self.combo_resolutions)

        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.toggle_camera)
        controls.addWidget(self.btn_start)

        controls.addWidget(QLabel("Rotate:"))
        self.rot_slider = QSlider(Qt.Horizontal)
        self.rot_slider.setRange(0, 360)
        self.rot_slider.valueChanged.connect(self.rotate_video)
        controls.addWidget(self.rot_slider)

        layout.addLayout(controls)
        layout.addWidget(self.view)  # Add the view to the layout so it expands

        # --- INIT ---
        self.initialize_camera_list()
        self.combo_cameras.currentIndexChanged.connect(self.on_camera_changed)
        self.combo_resolutions.currentIndexChanged.connect(self.on_resolution_changed)

        if self.available_cameras:
            self.on_camera_changed(self.combo_cameras.currentIndex())
            self.toggle_camera()

    # [KEY CHANGE 3] The Resize Event
    # This acts as a "Listener" for when you change the window size.
    def resizeEvent(self, event):
        # Let the standard resize happen first
        super().resizeEvent(event)

        # Then, force the View to fit the Video Item exactly
        self.fit_video_in_view()

    def fit_video_in_view(self):
        if self.video_item:
            # fitInView scales the SCENE coordinates to the VIEWport pixels
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def initialize_camera_list(self):
        """Populate the camera dropdown, prioritizing V4L2 devices."""
        self.available_cameras = QMediaDevices.videoInputs()
        self.combo_cameras.clear()

        best_index = 0
        for i, cam in enumerate(self.available_cameras):
            desc = cam.description()
            device_id = cam.id().data().decode().lower()
            self.combo_cameras.addItem(desc)

            # Smart Default: Look for "16MP" or "v4l2"
            if "16MP" in desc or "v4l2" in device_id:
                best_index = i

        if self.available_cameras:
            self.combo_cameras.setCurrentIndex(best_index)

    def on_camera_changed(self, index):
        """Handle user changing the camera source."""
        if index < 0 or index >= len(self.available_cameras):
            return

        # 1. Stop existing camera
        was_running = False
        if self.camera and self.camera.isActive():
            was_running = True
            self.camera.stop()

        # 2. Initialize new camera
        selected_device = self.available_cameras[index]
        self.camera = QCamera(selected_device)
        self.session.setCamera(self.camera)

        # 3. Populate resolutions for this camera
        self.populate_resolutions()

        # 4. Restart if it was running
        if was_running:
            self.camera.start()

    def populate_resolutions(self):
        """Populate resolution dropdown, prioritizing MJPEG."""
        self.combo_resolutions.blockSignals(
            True
        )  # Prevent triggering change while filling
        self.combo_resolutions.clear()

        self.available_formats = self.camera.cameraDevice().videoFormats()

        # Sort by width (descending)
        self.available_formats.sort(key=lambda f: f.resolution().width(), reverse=True)

        for i, fmt in enumerate(self.available_formats):

            width, height = (fmt.resolution().width(), fmt.resolution().height())
            pix_name = str(fmt.pixelFormat()).split(".")[-1]
            fps = fmt.maxFrameRate()

            label = f"{width}x{height} [{pix_name}] @ {fps} fps"
            self.combo_resolutions.addItem(label)

        self.combo_resolutions.setCurrentIndex(len(self.available_formats)//2) # set a resolution in the middle
        self.combo_resolutions.blockSignals(False)

        # Manually trigger the resolution update for the logic to apply
        self.on_resolution_changed(len(self.available_formats)//2)

    def on_resolution_changed(self, index):

        if index < 0:
            return
        fmt = self.available_formats[index]
        res = fmt.resolution()
        print(f"Resolution: {res.width()}x{res.height()}")

        was_running = self.camera.isActive()
        if was_running:
            self.camera.stop()
            QApplication.processEvents()

        self.camera.setCameraFormat(fmt)

        # Center and Refit immediately
        self.fit_video_in_view()

        if was_running:
            self.camera.start()

    def toggle_camera(self):
        if self.camera.isActive():
            self.camera.stop()
            self.btn_start.setText("Start")
        else:
            self.camera.start()
            self.btn_start.setText("Stop")

    def rotate_video(self, angle):
        # Set the origin point for rotation to the center of the item
        center = self.video_item.boundingRect().center()
        self.video_item.setTransformOriginPoint(center)
        self.video_item.setRotation(angle)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CameraSceneFix()
    window.show()
    sys.exit(app.exec())

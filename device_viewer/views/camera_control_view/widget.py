from venv import logger
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QComboBox, QLabel
from PySide6.QtMultimedia import QMediaCaptureSession, QCamera, QMediaDevices

from microdrop_style.colors import SECONDARY_SHADE, WHITE

ICON_FONT_FAMILY = "Material Symbols Outlined"

class CameraControlWidget(QWidget):

    available_cameras = []

    def __init__(self, model, capture_session: QMediaCaptureSession):
        super().__init__()
        self.model = model
        self.capture_session = capture_session
        self.camera = None  # Will be set when a camera is selected

        self.setStyleSheet(f"QPushButton {{ font-family: { ICON_FONT_FAMILY }; font-size: 22px; padding: 2px 2px 2px 2px; }} QPushButton:hover {{ color: { SECONDARY_SHADE[700] }; }} QPushButton:checked {{ background-color: { SECONDARY_SHADE[900] }; color: { WHITE }; }}")

        # Camera Combo Box
        self.camera_combo = QComboBox()
        self.camera_label = QLabel("Camera:")
        self.camera_refresh_button = QPushButton("refresh")
        self.camera_select_layout = QHBoxLayout()
        self.camera_select_layout.addWidget(self.camera_label)
        self.camera_select_layout.addWidget(self.camera_combo)
        self.camera_select_layout.addWidget(self.camera_refresh_button)

        # Make checkable buttons
        self.button_align = QPushButton("view_in_ar")
        self.button_align.setToolTip("Align Camera")

        self.button_reset = QPushButton("frame_reload")
        self.button_reset.setToolTip("Reset Camera")

        # btn_layout
        btn_layout = QHBoxLayout()
        for btn in [self.button_align]:
            btn.setCheckable(True)
            btn_layout.addWidget(btn)
        btn_layout.addWidget(self.button_reset)
        
        # Main layout
        layout = QVBoxLayout()

        layout.addLayout(self.camera_select_layout)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.sync_buttons_and_label()

        self.button_align.clicked.connect(lambda: self.set_mode("camera-place"))
        self.button_reset.clicked.connect(self.reset)
        self.camera_refresh_button.clicked.connect(self.populate_camera_list)
        self.camera_combo.currentIndexChanged.connect(self.set_camera_model)
        self.model.observe(self.on_mode_changed, "mode")

        self.populate_camera_list()

    def on_mode_changed(self, event):
            self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        """Set checked states and label based on model.mode."""
        self.button_align.setChecked(self.model.mode == "camera-place")

    def populate_camera_list(self):
        """Populate the camera combo box with available cameras."""
        self.available_cameras = QMediaDevices.videoInputs()
        print(f"Available cameras: {[c.description() for c in self.available_cameras]}")
        self.camera_combo.clear()
        # Add descriptions to the combo box
        for camera in self.available_cameras:
            self.camera_combo.addItem(camera.description())

    def set_camera_model(self, index):
        if self.camera:
            # If you already have a camera instance, delete or stop it
            self.camera.stop()
            self.camera = None
        if 0 <= index < len(self.available_cameras):
            self.camera = QCamera(self.available_cameras[index])
            self.capture_session.setCamera(self.camera)
            self.camera.start()
            print("Camera set to:", self.available_cameras[index].description())


    def set_mode(self, mode):
        self.model.mode = mode

    def reset(self):
        """Reset the camera control widget to its initial state."""
        self.model.camera_perspective.reset()
        if self.model.mode == "camera-edit":
            self.model.mode = "camera-place"  # Reset to camera-place mode after reset
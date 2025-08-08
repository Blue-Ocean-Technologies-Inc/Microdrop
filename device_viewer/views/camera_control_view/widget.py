from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QComboBox, QLabel, QGraphicsScene, QGraphicsPixmapItem, QStyleOptionGraphicsItem
from PySide6.QtCore import Slot, QTimer, QStandardPaths, QObject, QThread, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap, QTransform
from PySide6.QtMultimedia import QMediaCaptureSession, QCamera, QMediaDevices, QVideoFrameFormat, QVideoFrameInput, QVideoFrame
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
import cv2
import time
import os
import subprocess

from microdrop_style.colors import SECONDARY_SHADE, WHITE, SUCCESS_COLOR
from device_viewer.utils.camera import qimage_to_cv_image, cv_image_to_qimage
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

ICON_FONT_FAMILY = "Material Symbols Outlined"

class CameraControlWidget(QWidget):

    def __init__(self, model, capture_session: QMediaCaptureSession, video_item: QGraphicsVideoItem, pixmap_item: QGraphicsPixmapItem, scene: QGraphicsScene):
        super().__init__()
        self.model = model
        self.capture_session = capture_session
        self.scene = scene
        self.pixmap_item = pixmap_item
        self.video_item = video_item  # The video item for the camera feed
        self.camera = None  # Will be set when a camera is selected
        self.qt_available_cameras = None
        self.cv2_available_cameras = []  # List of available cameras using OpenCV
        self.using_opencv = False  # Flag to indicate if OpenCV is being used for camera
        self.camera_formats = None  # Will be set when a camera is selected
        self.recording_timer = QTimer()  # Timer to handle recording state
        self.video_writer = None  # Video writer for recording
        self.recording_file_path = None  # Path to the video file being recorded
        self.frame_count = 0  # Frame count for video recording
        self.record_start_ts = None  # Timestamp when recording starts

        self.cap = None  # OpenCV VideoCapture object
        self.frame_input = None
        self.frame_input_timer = QTimer()  # Timer to handle frame input

        self.capture_success_timer = QTimer() # Timer to reset the capture button style after a successful capture
        self.capture_success_timer.setSingleShot(True)
        self.capture_success_timer.timeout.connect(self.reset_capture_button_style)

        self.setStyleSheet(f"QPushButton {{ font-family: { ICON_FONT_FAMILY }; font-size: 22px; padding: 2px 2px 2px 2px; }} QPushButton:hover {{ color: { SECONDARY_SHADE[700] }; }} QPushButton:checked {{ background-color: { SECONDARY_SHADE[900] }; color: { WHITE }; }}")

        # Camera Combo Box
        self.camera_combo = QComboBox()
        self.camera_label = QLabel("Camera:")
        self.resolution_combo = QComboBox()
        self.resolution_label = QLabel("Resolution: ")
        self.camera_select_layout = QHBoxLayout()
        self.camera_select_layout.addWidget(self.camera_label)
        self.camera_select_layout.addWidget(self.camera_combo)

        self.resolution_select_layout = QHBoxLayout()
        self.resolution_select_layout.addWidget(self.resolution_label)
        self.resolution_select_layout.addWidget(self.resolution_combo)
        
        # Make checkable buttons
        self.button_align = QPushButton("view_in_ar")
        self.button_align.setToolTip("Align Camera Perspective")

        self.button_reset = QPushButton("frame_reload")
        self.button_reset.setToolTip("Reset Camera Perspective")

        self.camera_refresh_button = QPushButton("refresh")
        self.camera_refresh_button.setToolTip("Refresh Camera List")

        # recording buttons
        recording_layout = QHBoxLayout()
        self.record_button = QPushButton("videocam")
        self.record_button.setToolTip("Start Recording")
        self.stop_record_button = QPushButton("stop")
        self.stop_record_button.setToolTip("Stop Recording")
        self.capture_image_button = QPushButton("photo_camera")
        self.capture_image_button.setToolTip("Capture Image")

        recording_layout.addWidget(self.record_button)
        recording_layout.addWidget(self.stop_record_button)
        recording_layout.addWidget(self.capture_image_button)

        # btn_layout
        btn_layout = QHBoxLayout()
        for btn in [self.button_align]:
            btn.setCheckable(True)
            btn_layout.addWidget(btn)
        btn_layout.addWidget(self.button_reset)
        btn_layout.addWidget(self.camera_refresh_button)
        
        # Main layout
        layout = QVBoxLayout()

        layout.addLayout(self.camera_select_layout)
        layout.addLayout(self.resolution_select_layout)
        layout.addLayout(recording_layout)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.sync_buttons_and_label()

        self.button_align.clicked.connect(lambda: self.set_mode("camera-place"))
        self.button_reset.clicked.connect(self.reset)
        self.capture_image_button.clicked.connect(self.capture_button_handler)
        self.record_button.clicked.connect(self.video_record_start)
        self.stop_record_button.clicked.connect(self.video_record_stop)
        self.recording_timer.timeout.connect(self.video_record_frame_handler)
        self.camera_refresh_button.clicked.connect(self.populate_camera_list)
        self.camera_combo.currentIndexChanged.connect(self.set_camera_model)
        self.resolution_combo.currentIndexChanged.connect(self.set_resolution)
        self.frame_input_timer.timeout.connect(self.render_frame)
        self.model.observe(self.on_mode_changed, "mode")

        self.populate_camera_list()

    def on_mode_changed(self, event):
            self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        """Set checked states and label based on model.mode."""
        self.button_align.setChecked(self.model.mode == "camera-place")

    def populate_camera_list(self):
        """Populate the camera combo box with available cameras."""
        old_camera_name = self.camera_combo.currentText() if self.camera_combo.currentText() else None
        self.camera_combo.clear()
        self.qt_available_cameras = QMediaDevices.videoInputs() if os.getenv("USE_CV2", "0") != "1" else []
        self.cv2_available_cameras = []

        if len(self.qt_available_cameras) > 0: # We can use Qt camera detection
            self.using_opencv = False  # Using Qt cameras
            
            # Add descriptions to the combo box
            for camera in self.qt_available_cameras:
                self.camera_combo.addItem(camera.description())

            # Set the current index to the previously selected camera if it exists
            if old_camera_name:
                for i, camera in enumerate(self.qt_available_cameras):
                    if camera.description() == old_camera_name:
                        self.camera_combo.setCurrentIndex(i)
                        break
        else:  # No cameras found, use cv2 to list cameras
            self.using_opencv = True  # Using OpenCV cameras
            logger.warning("No cameras found using Qt. Attempting to list cameras using OpenCV.")
            for i in range(5):  # Check first 5 indices for cameras
                self.cv2_available_cameras.append(i)
                self.camera_combo.addItem(f"Camera #{i}")

    def set_camera_model(self, index):
        if self.camera:
            # If you already have a camera instance, delete or stop it
            self.camera.stop()
            self.camera = None

        if self.cap:
            self.cap.release()
            self.cap = None

        if self.frame_input_timer.isActive():
            self.frame_input_timer.stop()

        if not self.using_opencv:  # If Qt cameras are available
            self.video_item.setVisible(True)
            self.pixmap_item.setVisible(False)  # Hide the pixmap item if using Qt
            if 0 <= index < len(self.qt_available_cameras):
                self.camera = QCamera(self.qt_available_cameras[index])
                self.camera_formats = list(filter(lambda fmt: fmt.pixelFormat() != QVideoFrameFormat.PixelFormat.Format_YUYV, self.qt_available_cameras[index].videoFormats())) # Selectng these formats gets a segfault for some reason
                self.capture_session.setCamera(self.camera)
                self.camera.start()
        else: # If no Qt cameras are available, use OpenCV camera
            self.video_item.setVisible(False)
            self.pixmap_item.setVisible(True)  # Show the pixmap item if using OpenCV
            if 0 <= index < len(self.cv2_available_cameras):
                self.cap = cv2.VideoCapture(self.cv2_available_cameras[index])
                self.frame_input_timer.start(30)  # Start the timer to render frames every 30 ms

        self.populate_resolution_list()

    @Slot()
    def render_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return

        image = cv_image_to_qimage(frame)

        self.pixmap_item.setPixmap(QPixmap.fromImage(image))
        self.scene.update()  # Update the scene to reflect the new pixmap
    def populate_resolution_list(self):
        """Populate the resolution combo box with available resolutions."""
        if not self.using_opencv:
            if self.camera:
                self.resolution_combo.clear()

                for format in self.camera_formats:
                    res = format.resolution()
                    self.resolution_combo.addItem(f"{res.width()}x{res.height()}")
        else:
            # For OpenCV, we can set a fixed resolution or use the camera's default
            self.resolution_combo.clear()

            common_resolutions = [
                (640, 480),
                (800, 600),
                (1024, 768),
                (1280, 720),
                (1920, 1080),
                (3840, 2160),
            ]

            current_resolution = (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            if current_resolution != (0, 0):
                if current_resolution in common_resolutions:
                    common_resolutions.remove(current_resolution)  # Remove current resolution if it exists in the list
                common_resolutions.insert(0, current_resolution)  # Add current resolution as the first option

            for width, height in common_resolutions:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                
                actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                if (actual_width, actual_height) == (width, height):
                    self.resolution_combo.addItem(f"{width}x{height}")
            
            # Set the current index to the first resolution
            self.set_resolution(0)  # Set the resolution to the first item in the list
        

    def set_resolution(self, index):
        """Set the camera resolution based on the selected index."""
        if self.resolution_combo.count() == 0:
            logger.warning("No resolutions available to set.")
            return

        if not self.using_opencv:
            if self.camera and 0 <= index < len(self.camera_formats):
                format = self.camera_formats[index]
                self.camera.setCameraFormat(format)
                self.model.camera_perspective.camera_resolution = (format.resolution().width(), format.resolution().height())
        else:
            if self.cap:
                resolution = self.resolution_combo.itemText(index)
                width, height = map(int, resolution.split('x'))
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                self.model.camera_perspective.camera_resolution = (width, height)

    def get_next_image_id(self):
        """Generate a unique image ID for captured images."""
        return str(int(time.time()))

    def get_transformed_frame(self):
        """Apply a transformation to the video frame."""

        image = QImage(self.scene.width(), self.scene.height(), QImage.Format_ARGB32)
        image.fill(0xFF000000)  # Fill with black background

        if self.model.camera_perspective:
            painter = QPainter(image)
            options = QStyleOptionGraphicsItem()
            scale = QTransform()
            if self.using_opencv:
                scale.scale(self.scene.width() / self.model.camera_perspective.camera_resolution[0],
                           self.scene.height() / self.model.camera_perspective.camera_resolution[1])
            painter.setTransform(scale * self.model.camera_perspective.transformation)
            if self.using_opencv:
                # If using OpenCV, draw the pixmap item
                self.pixmap_item.paint(painter, options, None)
            else:
                self.video_item.paint(painter, options, None)
            painter.end()
        return image
    # Callbacks

    @Slot()
    def capture_button_handler(self):
        """Callback for when the capture button is pressed."""
        self.capture_image_button.setStyleSheet(f"background-color: {SECONDARY_SHADE[900]};")
        image = self.get_transformed_frame()
        image.save(f"{QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)}/captured_image_{self.get_next_image_id()}.png", "PNG")
        self.capture_image_button.setStyleSheet(f"background-color: {SUCCESS_COLOR};")  # Indicate success with a different color
        self.capture_success_timer.start(1000)  # Reset style after 2 seconds

    @Slot()
    def video_record_stop(self):
        """Stop video recording."""
        self.recording_timer.stop()
        logger.info("Video recording stopped.")
        if self.video_writer:
            self.video_writer.release()
            logger.info("Video file saved.")

            recording_duration = time.time() - self.record_start_ts
            frames_per_second = self.frame_count / recording_duration if recording_duration > 0 else None

            if frames_per_second:
                # Use ffmpeg to recode with the correct frame rate
                logger.info(f"Re-encoding video with {frames_per_second} FPS.")
                subprocess.Popen(f"""ffmpeg -i {self.recording_file_path} -filter:v "setpts=(30/{frames_per_second})*PTS" {self.recording_file_path}@{int(frames_per_second)}fps.mp4; rm {self.recording_file_path}""", shell=True)
                logger.info("Video re-encoded successfully.")

            self.video_writer = None
            self.recording_file_path = None  # Reset the recording file path
            self.record_button.setStyleSheet("")
            self.stop_record_button.setStyleSheet("")

    @Slot()
    def video_record_start(self):
        """Start video recording."""
        if not self.video_writer:
            self.recording_file_path = f"{QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)}/video_recording_{self.get_next_image_id()}.mp4"
            self.video_writer = cv2.VideoWriter(self.recording_file_path,
                                        cv2.VideoWriter_fourcc(*'mp4v'),
                                        30,  # Frame rate
                                        (int(self.scene.width()), int(self.scene.height())))

            self.recording_timer.start(1000/30) # Example: record every 1/30th of a second
            self.frame_count = 0  # Reset frame count
            self.record_start_ts = time.time()  # Set the start timestamp
            self.record_button.setStyleSheet(f"background-color: {SECONDARY_SHADE[900]}; color: {WHITE};")
            self.stop_record_button.setStyleSheet(f"background-color: {SECONDARY_SHADE[900]}; color: {WHITE};")
            logger.info("Video recording started.")
        else:
            logger.warning("Video recording is already in progress.")
        

    @Slot()
    def video_record_frame_handler(self):
        """Handle video frame for recording."""
        frame = self.get_transformed_frame()
        if self.video_writer:
            self.video_writer.write(qimage_to_cv_image(frame))
            self.frame_count += 1

    @Slot()
    def reset_capture_button_style(self):
        """Reset the capture button style to its default state."""
        self.capture_image_button.setStyleSheet("")

    def set_mode(self, mode):
        self.model.mode = mode
        self.sync_buttons_and_label()

    def reset(self):
        """Reset the camera control widget to its initial state."""
        self.model.camera_perspective.reset()
        if self.model.mode == "camera-edit":
            self.model.mode = "camera-place"  # Reset to camera-place mode after reset
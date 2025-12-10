# -*- coding: utf-8 -*-
import os
import sys
import cv2
import time
import ctypes
import signal
import subprocess
import ctypes.util

from pathlib import Path
from apptools.preferences.api import Preferences
from PySide6.QtCore import Slot, QTimer, QStandardPaths, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QPushButton, QVBoxLayout, QComboBox,
                               QLabel, QGraphicsScene, QGraphicsPixmapItem, QStyleOptionGraphicsItem,
                               QSizePolicy, QApplication)
from PySide6.QtMultimedia import QMediaCaptureSession, QCamera, QMediaDevices, QVideoFrameFormat
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

from microdrop_style.colors import SECONDARY_SHADE, WHITE
from device_viewer.utils.camera import qimage_to_cv_image, cv_image_to_qimage
from logger.logger_service import get_logger
from microdrop_utils.status_bar_utils import set_status_bar_message
from microdrop_style.button_styles import get_complete_stylesheet

logger = get_logger(__name__)


class CameraControlWidget(QWidget):

    # Signals - we use them to not have to set up another dramatiq listener here. Listener is in device_view_pane.py
    camera_active_signal = Signal(bool)
    screen_capture_signal = Signal(object)
    screen_recording_signal = Signal(object)

    def __init__(self, model, capture_session: QMediaCaptureSession, video_item: QGraphicsVideoItem,
                 pixmap_item: QGraphicsPixmapItem, scene: QGraphicsScene, preferences: Preferences):
        super().__init__()
        self.preferences = preferences
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

        # Signal connectors
        self.camera_active_signal.connect(self.on_camera_active)
        self.screen_capture_signal.connect(self.capture_button_handler)
        self.screen_recording_signal.connect(self.on_recording_active)

        self.cap = None  # OpenCV VideoCapture object
        self.frame_input = None
        self.frame_input_timer = QTimer()  # Timer to handle frame input

        # Apply theme-aware styling
        self._apply_theme_styling()

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

        self.button_reset = QPushButton("reset_focus")
        self.button_reset.setToolTip("Reset Camera Perspective")

        self.camera_refresh_button = QPushButton("update")
        self.camera_refresh_button.setToolTip("Refresh Camera List")

        # Single toggle button for recording
        self.record_toggle_button = QPushButton("album")
        self.record_toggle_button.setToolTip("Start Recording Video")
        self.record_toggle_button.setCheckable(True)
        self.is_recording = False

        self.capture_image_button = QPushButton("camera")
        self.capture_image_button.setToolTip("Capture Image")

        ####### Rotate camera option #################
        self.rotate_camera_button = QPushButton("flip_camera_ios")
        self.rotate_camera_button.setToolTip("Rotate Camera")

        def _rotate_camera():
            self.scene.interaction_service.handle_rotate_camera()
        self.rotate_camera_button.clicked.connect(_rotate_camera)

        ######### Rotate device option ################
        self.rotate_device_button = QPushButton("rotate_90_degrees_cw")
        self.rotate_device_button.setToolTip("Rotate Device")

        def _rotate_device():
            self.scene.interaction_service.handle_rotate_device()

        self.rotate_device_button.clicked.connect(_rotate_device)

        ###### Single toggle button for camera on/off #####
        self.camera_toggle_button = QPushButton("videocam_off")
        self.camera_toggle_button.setToolTip("Camera Off")
        self.camera_toggle_button.setCheckable(True)
        self.is_camera_on = False
        self.camera_was_off_before_action = False  # Track if camera was off before capture/record

        # top buttons
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.capture_image_button)
        # top_layout.addWidget(self.record_button)
        # recording_layout.addWidget(self.stop_record_button)

        top_layout.addWidget(self.camera_toggle_button)
        top_layout.addWidget(self.camera_refresh_button)
        top_layout.addWidget(self.rotate_camera_button)

        # bottom buttons
        bottom_layout = QHBoxLayout()
        for btn in [self.record_toggle_button, self.button_align]:
            btn.setCheckable(True)
            bottom_layout.addWidget(btn)
        bottom_layout.addWidget(self.button_reset)
        bottom_layout.addWidget(self.rotate_device_button)
        
        # bottom_layout.addStretch()  # Add stretch to push buttons to the left and expand the layout
        
        # Main layout
        layout = QVBoxLayout()

        layout.addLayout(self.camera_select_layout)
        layout.addLayout(self.resolution_select_layout)
        layout.addLayout(top_layout)
        layout.addLayout(bottom_layout)
        self.setLayout(layout)
        
        # Set size policy to allow horizontal expansion but keep natural height
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.sync_buttons_and_label()

        # Connect toggle buttons with proper toggle logic
        self.camera_toggle_button.clicked.connect(self.toggle_camera)
        self.button_align.clicked.connect(self.toggle_align_camera_mode)
        self.button_reset.clicked.connect(self.reset)
        self.capture_image_button.clicked.connect(self.capture_button_handler)
        self.record_toggle_button.clicked.connect(self.toggle_recording)
        self.recording_timer.timeout.connect(self.video_record_frame_handler)
        self.camera_refresh_button.clicked.connect(self.populate_camera_list)
        self.camera_combo.currentIndexChanged.connect(self.set_camera_model)
        self.resolution_combo.currentIndexChanged.connect(self.set_resolution)
        self.frame_input_timer.timeout.connect(self.render_frame)
        self.model.observe(self.on_mode_changed, "mode")

        self.populate_camera_list()
        
        # Check initial camera state
        self.check_initial_camera_state()

    def turn_on_camera(self):
        self.preferences.set("camera.camera_state", "on")
        if self.camera:
            self.camera.start()
            self.is_camera_on = True
            self.camera_toggle_button.setText("videocam")
            self.camera_toggle_button.setToolTip("Camera On")
            self.camera_toggle_button.setChecked(True)

    def turn_off_camera(self):
        self.preferences.set("camera.camera_state", "off")
        if self.camera:
            self.camera.stop()
            self.is_camera_on = False
            self.camera_toggle_button.setText("videocam_off")
            self.camera_toggle_button.setToolTip("Camera Off")
            self.camera_toggle_button.setChecked(False)

    def toggle_camera(self):
        """Toggle camera on/off state."""
        if self.is_camera_on:
            self.turn_off_camera()
            self.is_camera_on = False
            self.camera_toggle_button.setText("videocam_off")
            self.camera_toggle_button.setToolTip("Camera Off")
            self.camera_toggle_button.setChecked(False)
        else:
            self.turn_on_camera()
            self.is_camera_on = True
            self.camera_toggle_button.setText("videocam")
            self.camera_toggle_button.setToolTip("Camera On")
            self.camera_toggle_button.setChecked(True)

    def toggle_recording(self):
        """Toggle recording on/off state."""
        if self.is_recording:
            self.video_record_stop()
        else:
            self.video_record_start()

    def toggle_align_camera_mode(self):

        if self.model.mode == "camera-edit" or (self.model.mode != "camera-edit" and self.can_enter_edit_mode()):
            logger.debug(f"Toggle align camera mode: camera-edit. Current mode: {self.model.mode}")
            self.model.flip_mode_activation("camera-edit")
        else:
            logger.debug(f"Toggle align camera mode: camera-place. Current mode: {self.model.mode}")
            self.model.flip_mode_activation("camera-place")

    def can_enter_edit_mode(self) -> bool:
        """
        Return True if camera edit mode is possible.

        Camera edit only possible when camera placement has worked and a perspective transformation can be done
        """
        return self.model.camera_perspective.perspective_transformation_possible()

    def _apply_theme_styling(self):
        """Apply theme-aware styling to the widget."""
        try:
            # Import here to avoid circular imports
            from microdrop_style.helpers import is_dark_mode

            theme = "dark" if is_dark_mode() else "light"
            # Use complete stylesheet with tooltips for icon buttons
            icon_button_style = get_complete_stylesheet(theme, "default")
            self.setStyleSheet(icon_button_style)
        except Exception as e:
            # Fallback to light theme if there's an error
            icon_button_style = get_complete_stylesheet("light", "default")
            self.setStyleSheet(icon_button_style)

    def update_theme_styling(self, theme="light"):
        """Update styling when theme changes."""
        icon_button_style = get_complete_stylesheet(theme, "default")
        self.setStyleSheet(icon_button_style)

    # --------------------- Callbacks ---------------------------------------
    @Slot(bool)
    def on_camera_active(self, active):
        if active:
            self.turn_on_camera()
        else:
            self.turn_off_camera()

    @Slot(bool)
    def on_recording_active(self, recording_data):
        if isinstance(recording_data, dict):
            action = recording_data.get("action", "").lower()
            if action == "start":
                directory = recording_data.get("directory")
                step_description = recording_data.get("step_description")
                step_id = recording_data.get("step_id")
                self.video_record_start(directory, step_description, step_id)
            elif action == "stop":
                self.video_record_stop()
        else:
            if recording_data:
                self.video_record_start()
            else:
                self.video_record_stop()


    def on_mode_changed(self, event):
        self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        """Set checked states and label based on model.mode."""
        if self.model.mode == "camera-place":
            self.button_align.setStyleSheet(self.button_reset.styleSheet())
            self.button_align.setChecked(True)


        elif self.model.mode == "camera-edit":
            self.button_align.setChecked(True)
            self.button_align.setStyleSheet("background-color: green;")

        else:
            self.button_align.setChecked(False)
            self.button_align.setStyleSheet(self.button_reset.styleSheet())

    def reset(self):
        """Reset the camera control widget to its initial state."""
        self.model.camera_perspective.reset()
        if self.model.mode == "camera-edit":
            # Reset to camera-place mode after reset
            self.model.mode = "camera-place"

    def populate_camera_list(self):
        """Populate the camera combo box with available cameras."""
        preferences_camera = self.preferences.get("camera.selected_camera", None)
        if preferences_camera:
            old_camera_name = preferences_camera
        else:
            old_camera_name = self.camera_combo.currentText() if self.camera_combo.currentText() else None
        
        self.camera_combo.clear()
        self.qt_available_cameras = QMediaDevices.videoInputs() if os.getenv("USE_CV2", "0") != "1" else []
        self.qt_available_cameras.append(None)
        self.cv2_available_cameras = []

        if len(self.qt_available_cameras) > 0: # We can use Qt camera detection
            self.using_opencv = False  # Using Qt cameras
            
            # Add descriptions to the combo box
            self.camera_combo.blockSignals(True)  # Block signals
            for camera in self.qt_available_cameras:
                self.camera_combo.addItem(camera.description() if camera else "<No Camera>")
            self.camera_combo.blockSignals(False)  # Re-enable signals
            self.camera_combo.setCurrentIndex(-1) # No selection initially, so selection at position 0 fires if chosen by below logic

            # Set the current index to the previously selected camera if it exists (make sure something is selected here)
            if old_camera_name:
                found_flag = False
                for i, camera in enumerate(self.qt_available_cameras):
                    if camera and camera.description() == old_camera_name:
                        self.camera_combo.setCurrentIndex(i)
                        found_flag = True
                        break
                if not found_flag:
                    self.camera_combo.setCurrentIndex(0)
            else:
                self.camera_combo.setCurrentIndex(0)
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
                if self.qt_available_cameras[index]: # Camera is not None
                    self.camera = QCamera(self.qt_available_cameras[index])
                    # Use ram NV12 format
                    filtered_formats = [format for format in self.qt_available_cameras[index].videoFormats()
                                        if (format.pixelFormat() == QVideoFrameFormat.PixelFormat.Format_NV12) or
                                           (format.pixelFormat() == QVideoFrameFormat.PixelFormat.Format_NV21)]
                    # Use all alternative formats when raw isn't available but skip YUV because it gets a segfault
                    if len(filtered_formats) == 0:
                        filtered_formats = [format for format in self.qt_available_cameras[index].videoFormats()
                                            if format.pixelFormat() != QVideoFrameFormat.PixelFormat.Format_YUYV]
                    # Sort resolutions
                    filtered_formats.sort(key=lambda f: f.resolution().width() * f.resolution().height())
                    self.camera_formats = {f"{f.resolution().width()}x{f.resolution().height()}": f
                                           for f in filtered_formats}
                    self.capture_session.setCamera(self.camera)
                    if self.preferences.get("camera.camera_state", "off") == "on":
                        self.camera.start()
        else: # If no Qt cameras are available, use OpenCV camera
            self.video_item.setVisible(False)
            self.pixmap_item.setVisible(True)  # Show the pixmap item if using OpenCV
            if 0 <= index < len(self.cv2_available_cameras):
                self.cap = cv2.VideoCapture(self.cv2_available_cameras[index])
                self.cap.set(cv2.CAP_PROP_FPS, 30)  # Set a default FPS
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'mp4v'))
                self.frame_input_timer.start(30)  # Start the timer to render frames every 30 ms

        self.populate_resolution_list()

    def populate_resolution_list(self):
        """Populate the resolution combo box with available resolutions."""
        if not self.using_opencv:
            if self.camera:
                self.resolution_combo.clear()

                preferences_resolution = self.preferences.get("camera.resolution", None)

                for res in self.camera_formats:
                    self.resolution_combo.addItem(res)

                if preferences_resolution:
                    index = self.resolution_combo.findText(preferences_resolution)
                    if index != -1:
                        self.resolution_combo.setCurrentIndex(index)
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
                resolution = self.resolution_combo.itemText(index)
                self.preferences.set("camera.resolution", resolution)
                format = self.camera_formats[resolution]

                camera_on = self.camera.isActive()
                if camera_on:
                    self.camera.stop()
                    QApplication.processEvents()

                self.camera.setCameraFormat(format)
                self.model.camera_perspective.camera_resolution = (format.resolution().width(), format.resolution().height())
                if camera_on:
                    self.camera.start()
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
        """
        Returns the full high-res transformed image, automatically resizing
        the canvas and shifting the origin so nothing is clipped.
        """

        # 1. Get the source item and its original size
        target_item = self.pixmap_item if self.using_opencv else self.video_item

        # 3. where the image ends up after transformation
        # This gives us a rectangle that might have negative coordinates (e.g. x=-50)
        mapped_rect = self.video_item.sceneBoundingRect()

        # 4. Create the QImage based on this NEW size (so nothing is cut off)
        # If you strictly need the original camera_resolution, see Option 2 below
        width = int(mapped_rect.width())
        height = int(mapped_rect.height())
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(0x00000000)  # Transparent background (or use 0xFF000000 for black)

        painter = QPainter(image)
        options = QStyleOptionGraphicsItem()

        # Fix the clipping by shifting the Painter
        # If the image starts at -50, we translate +50 to bring it to 0
        painter.translate(-mapped_rect.x(), -mapped_rect.y())

        # 6. Apply the transformation
        # We use combine=True so we don't overwrite our translation
        painter.setTransform(self.video_item.transform(), combine=True)

        # 7. Paint the raw high-res item
        target_item.paint(painter, options, None)

        painter.end()
        return image
    
    # ------------------------ Callbacks -------------------------------

    @Slot()
    def render_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return

        image = cv_image_to_qimage(frame)

        self.pixmap_item.setPixmap(QPixmap.fromImage(image))
        self.scene.update()  # Update the scene to reflect the new pixmap

    @Slot()
    def capture_button_handler(self, capture_data=None):
        """Callback for when the capture button is pressed."""
        directory = None
        step_description = None
        step_id = None
        
        # extract data if provided
        if isinstance(capture_data, dict):
            directory = capture_data.get("directory")
            step_description = capture_data.get("step_description")
            step_id = capture_data.get("step_id")
            
        # Ensure camera is on for capture
        was_camera_off = not self.ensure_camera_on()
        
        # Capture the image
        image = self.get_transformed_frame()

        # generate filename
        filename = self._generate_capture_filename(step_description, step_id)

        # determine save path
        if directory:
            save_path = Path(directory) / "captures" / filename 
            # Ensure directory exists
            save_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # use default location
            save_path = Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)) / filename

        image.save(str(save_path), "PNG")
        logger.info("Image captured successfully")
        
        # Show status bar message
        try:
            # Try to find the main window through the widget hierarchy
            parent = self.parent()
            while parent and not hasattr(parent, '_statusbar'):
                parent = parent.parent()
            
            if parent and hasattr(parent, '_statusbar'):
                set_status_bar_message("Image captured successfully", parent, 5000)
            else:
                # Fallback to using GUI.invoke_later
                from pyface.api import GUI
                GUI.invoke_later(set_status_bar_message, "Image captured successfully", None, 5000)
        except Exception as e:
            logger.debug(f"Failed to show status bar message: {e}")
        
        # Restore camera state if we turned it on
        if was_camera_off:
            self.restore_camera_state()

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

                PR_SET_PDEATHSIG = 1

                def set_pdeathsig(): # https://blog.raylu.net/2021/04/01/set_pdeathsig.html
                    libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
                    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL) != 0:
                        raise OSError(ctypes.get_errno(), 'SET_PDEATHSIG')
                
                scale_factor = 30 / frames_per_second
                out_path = f"{self.recording_file_path}@{int(frames_per_second)}fps.mp4"

                cmd = [
                    "ffmpeg",
                    "-itsscale", str(scale_factor),   # must be before -i
                    "-i", self.recording_file_path,
                    "-c", "copy",
                    out_path,
                ]

                if sys.platform.startswith("linux"):
                    subprocess.Popen(" ".join(cmd),
                                    shell=True,
                                    preexec_fn=set_pdeathsig,
                                    stdin=subprocess.DEVNULL)
                else:
                    subprocess.Popen(cmd,
                                    shell=True)
                logger.info("Video re-encoded successfully.")

            self.video_writer = None
            self.recording_file_path = None  # Reset the recording file path
            self.record_toggle_button.setStyleSheet("")
            self.record_toggle_button.setChecked(False)  # Ensure it's unchecked
            self.is_recording = False
            
            # Show status bar message
            try:
                # Try to find the main window through the widget hierarchy
                parent = self.parent()
                while parent and not hasattr(parent, '_statusbar'):
                    parent = parent.parent()
                
                if parent and hasattr(parent, '_statusbar'):
                    set_status_bar_message("Video recording stopped and saved", parent, 5000)
                else:
                    # Fallback to using GUI.invoke_later
                    from pyface.api import GUI
                    GUI.invoke_later(set_status_bar_message, "Video recording stopped and saved", None, 5000)
            except Exception as e:
                logger.debug(f"Failed to show status bar message: {e}")
            
            # Restore camera state if we turned it on for recording
            if hasattr(self, 'camera_was_off_before_action') and self.camera_was_off_before_action:
                self.restore_camera_state()

    @Slot()
    def video_record_start(self, directory=None, step_description=None, step_id=None):
        """Start video recording."""
        if not self.video_writer:
            # Ensure camera is on for recording
            was_camera_off = not self.ensure_camera_on()
            
            # generate filename
            filename = self._generate_recording_filename(step_description, step_id)
            
            # determine save path
            if directory:
                save_path = Path(directory) / "recordings" / filename
                # Ensure directory exists
                save_path.parent.mkdir(parents=True, exist_ok=True)
                self.recording_file_path = str(save_path)
            else:
                # Use default Movies location
                self.recording_file_path = str(Path(QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)) / filename)

            self.video_writer = cv2.VideoWriter(self.recording_file_path,
                                        cv2.VideoWriter_fourcc(*'mp4v'),
                                        30,  # Frame rate
                                        (int(self.scene.width()), int(self.scene.height())))

            self.recording_timer.start(1000/30) # Example: record every 1/30th of a second
            self.frame_count = 0  # Reset frame count
            self.record_start_ts = time.time()  # Set the start timestamp
            self.record_toggle_button.setStyleSheet(f"background-color: {SECONDARY_SHADE[900]}; color: {WHITE};")
            self.record_toggle_button.setChecked(True)  # Ensure it's checked
            self.is_recording = True
            logger.info(f"Video recording started: {self.recording_file_path}")
            
            # Show status bar message
            try:
                # Try to find the main window through the widget hierarchy
                parent = self.parent()
                while parent and not hasattr(parent, '_statusbar'):
                    parent = parent.parent()
                
                if parent and hasattr(parent, '_statusbar'):
                    set_status_bar_message("Video recording started", parent, 5000)
                else:
                    # Fallback to using GUI.invoke_later
                    from pyface.api import GUI
                    GUI.invoke_later(set_status_bar_message, "Video recording started", None, 5000)
            except Exception as e:
                logger.debug(f"Failed to show status bar message: {e}")
        else:
            logger.warning("Video recording is already in progress.")
        

    @Slot()
    def video_record_frame_handler(self):
        """Handle video frame for recording."""
        frame = self.get_transformed_frame()
        if self.video_writer:
            self.video_writer.write(qimage_to_cv_image(frame))
            self.frame_count += 1

    def ensure_camera_on(self):
        """Ensure camera is on, return True if it was already on, False if we had to turn it on."""
        if not self.is_camera_on:
            self.camera_was_off_before_action = True
            self.turn_on_camera()
            return False
        return True

    def restore_camera_state(self):
        """Restore camera to previous state if we turned it on for an action."""
        if self.camera_was_off_before_action:
            self.turn_off_camera()
            self.camera_was_off_before_action = False

    def check_initial_camera_state(self):
        """Check the initial camera state and update button accordingly."""
        # Check if camera is currently active
        if hasattr(self, 'camera') and self.camera:
            # For Qt cameras, we can check if they're active
            if hasattr(self.camera, 'isActive') and self.camera.isActive():
                self.is_camera_on = True
                self.camera_toggle_button.setText("videocam")
                self.camera_toggle_button.setToolTip("Camera On")
                self.camera_toggle_button.setChecked(True)
            else:
                self.is_camera_on = False
                self.camera_toggle_button.setText("videocam_off")
                self.camera_toggle_button.setToolTip("Camera Off")
                self.camera_toggle_button.setChecked(False)
        else:
            # No camera instance, assume off
            self.is_camera_on = False
            self.camera_toggle_button.setText("videocam_off")
            self.camera_toggle_button.setToolTip("Camera Off")
            self.camera_toggle_button.setChecked(False)

    def _generate_capture_filename(self, step_description=None, step_id=None):
        timestamp = self.get_next_image_id()
        
        if step_description and step_id:
            clean_desc = "".join(c for c in step_description if c.isalnum() or c in (' ', '-', '_')).rstrip()
            clean_desc = clean_desc.replace(' ', '_')
            return f"{clean_desc}_{step_id}_{timestamp}.png"
        elif step_id:
            return f"step_{step_id}_{timestamp}.png"
        else:
            return f"captured_image_{timestamp}.png"
        
    def _generate_recording_filename(self, step_description=None, step_id=None):
        timestamp = self.get_next_image_id()
        
        if step_description and step_id:
            clean_desc = "".join(c for c in step_description if c.isalnum() or c in (' ', '-', '_')).rstrip()
            clean_desc = clean_desc.replace(' ', '_')
            return f"{clean_desc}_{step_id}_{timestamp}.mp4"
        elif step_id:
            return f"step_{step_id}_{timestamp}.mp4"
        else:
            return f"video_recording_{timestamp}.mp4"
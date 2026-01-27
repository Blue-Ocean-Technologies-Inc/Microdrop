import shutil
import sys
import time
import ctypes
import signal
import subprocess
import ctypes.util

from pathlib import Path
from apptools.preferences.api import Preferences
from pyface.qt.QtCore import Slot, QTimer, QStandardPaths, Signal, QUrl
from pyface.qt.QtGui import QImage, QPainter
from pyface.qt.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QComboBox,
    QLabel,
    QGraphicsScene,
    QStyleOptionGraphicsItem,
    QSizePolicy,
    QApplication,
)
from pyface.qt.QtMultimedia import QMediaCaptureSession, QCamera, QMediaDevices
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem
from microdrop_application.dialogs.pyface_wrapper import information, error, warning

from device_viewer.views.camera_control_view.preferences import CameraPreferences
from microdrop_style.colors import SECONDARY_SHADE, WHITE
from logger.logger_service import get_logger
logger = get_logger(__name__)

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ...models.media_capture_model import MediaCaptureMessageModel, MediaType
from protocol_grid.consts import DEVICE_VIEWER_MEDIA_CAPTURED


class CameraControlWidget(QWidget):

    # Signals - we use them to not have to set up another dramatiq listener here. Listener is in device_view_pane.py
    camera_active_signal = Signal(bool)
    screen_capture_signal = Signal(object)
    screen_recording_signal = Signal(object)

    def __init__(
        self,
        model,
        video_item: QGraphicsVideoItem,
        scene: QGraphicsScene,
        preferences: Preferences,
    ):

        super().__init__()
        self.model = model
        self.video_item = video_item  # The video item for the camera feed
        self.scene = scene
        self.preferences = CameraPreferences(preferences=preferences)

        self.preferences.observe(
            self._preferred_video_format_change, "preferred_video_format"
        )

        self.preferences.observe(
            self._preferred_video_format_change, "strict_video_format"
        )

        self.session = QMediaCaptureSession()
        self.camera = None  # Will be set when a camera is selected
        self.available_cameras = None
        self.available_formats = None  # Will be set when a camera is selected
        self.show_media_capture_dialog = True

        self.scene.addItem(self.video_item)
        self.session.setVideoOutput(self.video_item)

        self.recording_timer = QTimer()  # Timer to handle recording state
        self.recording_file_path = None  # Path to the video file being recorded
        self.ffmpeg_process = None

        # Signal connectors
        self.camera_active_signal.connect(self.on_camera_active)
        self.screen_capture_signal.connect(self.capture_button_handler)
        self.screen_recording_signal.connect(self.on_recording_active)

        # Camera Combo Box
        self.combo_cameras = QComboBox()
        self.camera_label = QLabel("Camera:")
        self.combo_resolutions = QComboBox()
        self.resolution_label = QLabel("Resolution: ")
        self.camera_select_layout = QHBoxLayout()
        self.camera_select_layout.addWidget(self.camera_label)
        self.camera_select_layout.addWidget(self.combo_cameras)

        self.resolution_select_layout = QHBoxLayout()
        self.resolution_select_layout.addWidget(self.resolution_label)
        self.resolution_select_layout.addWidget(self.combo_resolutions)

        # Make checkable buttons
        self.button_align = QPushButton("view_in_ar")
        self.button_align.setToolTip("Align Camera Perspective")

        self.button_reset = QPushButton("reset_focus")
        self.button_reset.setToolTip("Reset Camera Perspective")

        self.camera_refresh_button = QPushButton("flip_camera_ios")
        self.camera_refresh_button.setToolTip("Refresh Camera List")

        # Single toggle button for recording
        self.record_toggle_button = QPushButton("album")
        self.record_toggle_button.setToolTip("Start Recording Video")
        self.record_toggle_button.setCheckable(True)
        self.is_recording = False

        self.capture_image_button = QPushButton("camera")
        self.capture_image_button.setToolTip("Capture Image")

        ####### Rotate camera option #################
        self.rotate_camera_button = QPushButton("cameraswitch")
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
        self.camera_was_off_before_action = (
            False  # Track if camera was off before capture/record
        )

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
        self.camera_refresh_button.clicked.connect(self.initialize_camera_list)
        self.model.observe(self.on_mode_changed, "mode")
        self.combo_cameras.currentIndexChanged.connect(self.on_camera_changed)
        self.combo_resolutions.currentIndexChanged.connect(self.on_resolution_changed)

        # Check initial camera state
        self.initialize_camera_list()
        self.check_initial_camera_state()

    ############################## preference change observers ##############################

    def _preferred_video_format_change(self, event):
        strict_flag = "strictly" if self.preferences.strict_video_format else ""
        logger.critical(f"Preferred video format changed to: {self.preferences.preferred_video_format} {strict_flag}")
        self.populate_resolutions()

    ########################################################################################

    def turn_on_camera(self):
        logger.info("Turning camera on")
        self.preferences.camera_state = True
        if self.camera:
            self.camera.start()
            self.camera_toggle_button.setText("videocam")
            self.camera_toggle_button.setToolTip("Camera On")
            self.camera_toggle_button.setChecked(True)

    def turn_off_camera(self):
        logger.info("Turning camera off")
        self.preferences.camera_state = False
        if self.camera:
            self.camera.stop()
            self.camera_toggle_button.setText("videocam_off")
            self.camera_toggle_button.setToolTip("Camera Off")
            self.camera_toggle_button.setChecked(False)

    def toggle_camera(self):
        """Toggle camera on/off state."""
        self.turn_off_camera() if self.is_camera_on else self.turn_on_camera()
        self.is_camera_on = not self.is_camera_on

    def toggle_recording(self):
        """Toggle recording on/off state."""
        if self.is_recording:
            self.video_record_stop()
        else:
            self.video_record_start()

    def toggle_align_camera_mode(self):

        if self.model.mode == "camera-edit" or (
            self.model.mode != "camera-edit" and self.can_enter_edit_mode()
        ):
            logger.debug(
                f"Toggle align camera mode: camera-edit. Current mode: {self.model.mode}"
            )
            self.model.flip_mode_activation("camera-edit")
        else:
            logger.debug(
                f"Toggle align camera mode: camera-place. Current mode: {self.model.mode}"
            )
            self.model.flip_mode_activation("camera-place")

    def can_enter_edit_mode(self) -> bool:
        """
        Return True if camera edit mode is possible.

        Camera edit only possible when camera placement has worked and a perspective transformation can be done
        """
        return self.model.camera_perspective.perspective_transformation_possible()

    # --------------------- Callbacks ---------------------------------------
    @Slot(bool)
    def on_camera_active(self, active):
        if active:
            self.turn_on_camera()
        else:
            self.turn_off_camera()

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

    def initialize_camera_list(self):
        """Populate the camera combo box with available cameras."""
        preferences_camera = self.preferences.selected_camera

        if preferences_camera:
            old_camera_name = preferences_camera
        else:
            old_camera_name = (
                self.combo_cameras.currentText()
                if self.combo_cameras.currentText()
                else None
            )

        self.available_cameras = QMediaDevices.videoInputs()
        self.combo_cameras.clear()
        self.available_cameras.append(None)

        # Add descriptions to the combo box
        self.combo_cameras.blockSignals(True)  # Block signals
        for camera in self.available_cameras:
            self.combo_cameras.addItem(
                camera.description() if camera else "<No Camera>"
            )
        self.combo_cameras.blockSignals(False)  # Re-enable signals

        self.combo_cameras.setCurrentIndex(
            -1
        )  # No selection initially, so selection at position 0 fires if chosen by below logic

        # Set the current index to the previously selected camera if it exists (make sure something is selected here)
        if old_camera_name:
            for i, camera in enumerate(self.available_cameras):
                if camera and camera.description() == old_camera_name:
                    self.combo_cameras.setCurrentIndex(i)
                    return

        self.combo_cameras.setCurrentIndex(0)

    def on_camera_changed(self, index):
        """Handle user changing the camera source."""
        if index < 0 or index >= len(self.available_cameras):
            return
        elif not self.available_cameras[index]:  # Camera is not None
            return

        # Stop existing camera
        was_running = False
        if self.camera and self.camera.isActive():
            # If you already have a camera instance, delete or stop it
            self.camera.stop()
            was_running = True

        self.video_item.setVisible(True)

        # Initialize new camera
        self.camera = QCamera(self.available_cameras[index])
        self.session.setCamera(self.camera)
        self.preferences.selected_camera = self.available_cameras[index].description()

        # 3. Populate resolutions for this camera
        self.populate_resolutions()

        # 4. Restart if it was running
        if was_running:
            self.camera.start()

    def populate_resolutions(self, allow_strict_mode=True):
        """Populate the resolution combo box with available resolutions."""

        # Prevent triggering change while filling
        self.combo_resolutions.blockSignals(True)
        self.combo_resolutions.clear()

        # 1. Get all raw formats
        formats = self.camera.cameraDevice().videoFormats()

        def format_sort_key(fmt):
            """
            Sort hierarchy (Higher value = appears first):
            1. Resolution Width
            2. Resolution Height
            3. Is it the preferred format? (Bool)
            4. Max Frame Rate
            """
            res = fmt.resolution()
            # Helper to detect if this is our preferred format (returns 1 or 0)
            # We check the string representation safely
            fmt_name = str(fmt.pixelFormat()).upper()

            return (
                res.width(),
                res.height(),
                self.preferences.preferred_video_format.upper() in fmt_name,
                fmt.maxFrameRate(),
            )

        # 2. Sort the list descending based on our criteria
        # This puts the "Best" (Largest, Preferred, Fastest) formats at the top.
        formats.sort(key=format_sort_key, reverse=True)

        # 3. Deduplicate
        # Since the list is sorted, the first time we see a "Width x Height",
        # it is guaranteed to be the best version (MJPEG + High FPS).
        seen_resolutions = set()

        for fmt in formats:
            w, h = fmt.resolution().width(), fmt.resolution().height()
            res_key = (w, h)

            # if strict mode, only proceed if given format is the default video format
            fmt_name = str(fmt.pixelFormat()).upper()
            if self.preferences.strict_video_format and allow_strict_mode:
                if self.preferences.preferred_video_format.upper() not in fmt_name:
                    continue

            if res_key not in seen_resolutions:
                # Mark as seen
                seen_resolutions.add(res_key)

                # 4. Add to Combo
                # We construct a clean label
                fps = fmt.maxFrameRate()
                # Clean up pixel format name (e.g., "Format_MJPEG" -> "MJPEG")
                pix_name = str(fmt.pixelFormat()).split(".")[-1].replace("Format_", "")

                label = f"{w}x{h} [{pix_name}] @ {fps:.0f} fps"

                # KEY CHANGE: Store the actual 'fmt' object in the combo box item
                self.combo_resolutions.addItem(label, userData=fmt)

        # check if any resolutions found. else use strict mode if not already on.
        if len(seen_resolutions) > 0:

            self.combo_resolutions.blockSignals(False)
            self.combo_resolutions.setCurrentIndex(len(seen_resolutions) // 2)

        elif self.preferences.strict_video_format:
            warning_message = (f"Preferred video format <b>{self.preferences.preferred_video_format}</b> not supported by "
                               f"<b>{self.preferences.selected_camera}</b>.<br><br>"
                               f"Will ignore strict mode request for <b>{self.preferences.selected_camera}</b> ...")

            logger.warning(warning_message)
            warning(None, warning_message)

            self.populate_resolutions(allow_strict_mode=False)

    def on_resolution_changed(self, index):
        """Set the camera resolution based on the selected index."""
        if self.combo_resolutions.count() == 0:
            logger.warning("No resolutions available to set.")
            return

        if index < 0:
            return

        fmt = self.combo_resolutions.itemData(index)

        was_running = self.camera.isActive()
        if was_running:
            self.camera.stop()
            QApplication.processEvents()

        self.camera.setCameraFormat(fmt)

        resolution = self.combo_resolutions.itemText(index)
        logger.info(f"Camera Resolution Changed: {resolution}")

        self.preferences.resolution = resolution
        self.model.camera_perspective.camera_resolution = (
            fmt.resolution().width(),
            fmt.resolution().height(),
        )

        if was_running:
            self.camera.start()

    def get_next_image_id(self):
        """Generate a unique image ID for captured images."""
        return str(int(time.time()))

    # ------------------------ Callbacks -------------------------------

    @Slot()
    def capture_button_handler(self, capture_data=None):
        """Callback for when the capture button is pressed."""
        directory = None
        step_description = None
        step_id = None
        show_dialog = True

        # extract data if provided
        if isinstance(capture_data, dict):
            directory = capture_data.get("directory")
            step_description = capture_data.get("step_description")
            step_id = capture_data.get("step_id")
            show_dialog = capture_data.get("show_dialog")

        self.show_media_capture_dialog = show_dialog

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
            save_path = (
                Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation))
                / filename
            )

        image.save(str(save_path), "PNG")

        self._show_media_capture_dialog("Image", str(save_path))

        # Restore camera state if we turned it on
        if was_camera_off:
            self.restore_camera_state()

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
        if self.camera:
            # For Qt cameras, we can check if they're active
            if self.camera.isActive():
                self.is_camera_on = True
                self.camera_toggle_button.setText("videocam")
                self.camera_toggle_button.setToolTip("Camera On")
                self.camera_toggle_button.setChecked(True)
                return

        # else assume off
        self.is_camera_on = False
        self.camera_toggle_button.setText("videocam_off")
        self.camera_toggle_button.setToolTip("Camera Off")
        self.camera_toggle_button.setChecked(False)

    def _generate_capture_filename(self, step_description=None, step_id=None):
        timestamp = self.get_next_image_id()

        if step_description and step_id:
            clean_desc = "".join(
                c for c in step_description if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()
            clean_desc = clean_desc.replace(" ", "_")
            return f"{clean_desc}_{step_id}_{timestamp}.png"
        elif step_id:
            return f"step_{step_id}_{timestamp}.png"
        else:
            return f"captured_image_{timestamp}.png"

    def _generate_recording_filename(self, step_description=None, step_id=None):
        timestamp = self.get_next_image_id()

        if step_description and step_id:
            clean_desc = "".join(
                c for c in step_description if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()
            clean_desc = clean_desc.replace(" ", "_")
            return f"{clean_desc}_{step_id}_{timestamp}.mp4"
        elif step_id:
            return f"step_{step_id}_{timestamp}.mp4"
        else:
            return f"video_recording_{timestamp}.mp4"

    ##### Video recording #######
    def on_recording_active(self, recording_data):
        if isinstance(recording_data, dict):

            action = recording_data.get("action", "").lower()

            if action == "start":

                directory = recording_data.get("directory")
                step_description = recording_data.get("step_description")
                step_id = recording_data.get("step_id")
                show_dialog = recording_data.get("show_dialog", True)

                self.video_record_start(directory, step_description, step_id, show_dialog)

            elif action == "stop":
                self.video_record_stop()
        else:
            logger.error(
                f"Invalid recording data: {recording_data}. Needs to be a json dict."
            )

    # --- Transformation Logic ---
    def get_transformed_frame(self):
        """
        Captures the visual state of the camera item including:
        - Rotation
        - Perspective Alignment
        - Scaling
        """
        # Get the bounding rect of the item in the scene (after transforms)
        mapped_rect = self.video_item.sceneBoundingRect()
        width = int(mapped_rect.width())
        height = int(mapped_rect.height())

        # Create empty transparent image
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(0x00000000)

        painter = QPainter(image)
        options = QStyleOptionGraphicsItem()

        # Shift origin so we paint the whole rotated/transformed item
        painter.translate(-mapped_rect.x(), -mapped_rect.y())
        # Apply the item's transform (rotation, perspective, etc)
        painter.setTransform(self.video_item.transform(), combine=True)

        # Paint the video frame onto our image
        self.video_item.paint(painter, options, None)
        painter.end()
        return image

        # --- Video Recording with Transforms (FFmpeg Pipe) ---

    @Slot()
    def toggle_recording(self):
        if self.ffmpeg_process:
            self.video_record_stop()
        else:
            self.video_record_start()

    @Slot()
    def video_record_start(self, directory=None, step_description=None, step_id=None, show_dialog=True):
        if self.ffmpeg_process:
            return

        if not shutil.which("ffmpeg"):
            logger.error("FFmpeg not found.")
            error(
                self,
                "Error: Cannot start to record video",
                informative="FFmpeg not found.",
            )
            return

        # Ensure camera is on for capture
        was_camera_off = not self.ensure_camera_on()

        # Generate filename
        filename = self._generate_recording_filename(step_description, step_id)
        if directory:
            path = Path(directory) / "recordings" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            self.recording_file_path = str(path)

        else:
            self.recording_file_path = str(
                Path(QStandardPaths.writableLocation(QStandardPaths.MoviesLocation))
                / filename
            )

        self.show_media_capture_dialog = show_dialog

        # 1. Grab a sample frame to determine recording dimensions
        # This ensures the video size matches the transformed AR view
        sample_frame = self.get_transformed_frame()
        self.rec_width = sample_frame.width()
        self.rec_height = sample_frame.height()

        # Ensure dimensions are even (Required for H.264 / YUV420P)
        if self.rec_width % 2 != 0:
            self.rec_width -= 1
        if self.rec_height % 2 != 0:
            self.rec_height -= 1

        fps = int(
            self.combo_resolutions.currentData().maxFrameRate()
        )

        if not fps:
            fps = 15
        else:
            # adjust fps down to account for some frame loss since we have to manually apply transforms to frames
            fps = int(0.75 * fps)

        command = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{self.rec_width}x{self.rec_height}",
            "-pix_fmt",
            "rgba",
            "-r",
            str(fps),  # Fixed: Removed extra braces/f-string syntax
            "-i",
            "-",  # Fixed: "-i" and "-" must be separate items
            "-c:v",
            "libx264",  # Fixed: Split flag and value
            "-pix_fmt",
            "yuv420p",  # Fixed: Split flag and value
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-crf",
            "23",
            self.recording_file_path,
        ]

        # Linux specific: Kill ffmpeg if python dies
        def set_pdeathsig():
            if sys.platform.startswith("linux"):
                PR_SET_PDEATHSIG = 1
                libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
                libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL)

        try:
            self.ffmpeg_process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=set_pdeathsig if sys.platform.startswith("linux") else None,
            )

            # Start timer to feed frames to ffmpeg
            self.recording_timer.start(int(1000 / fps))
            self.record_toggle_button.setChecked(True)
            self.record_toggle_button.setStyleSheet(
                f"background-color: {SECONDARY_SHADE[900]}; color: {WHITE};"
            )

            logger.info(f"Recording started: {self.recording_file_path}")

        except Exception as e:
            logger.error(f"FFmpeg failed: {e}")
            error(
                self,
                "Error: Cannot start to record video",
                informative="FFmpeg failed.",
                detail=str(e),
            )
            self.ffmpeg_process = None

    @Slot()
    def video_record_frame_handler(self):
        """Grabs the transformed frame and pipes bytes to FFmpeg."""
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            # 1. Get the frame with transforms applied
            image = self.get_transformed_frame()

            # 2. Resize to match the initial recording dimensions
            # (Essential: video files cannot change resolution mid-stream)
            if image.width() != self.rec_width or image.height() != self.rec_height:
                image = image.scaled(self.rec_width, self.rec_height)

            # 3. Convert to RGBA8888 (Matches -pix_fmt rgba)
            if image.format() != QImage.Format_RGBA8888:
                image = image.convertToFormat(QImage.Format_RGBA8888)

            # 4. Write bytes to pipe
            try:
                # In PySide6, constBits() returns a memoryview.
                # subprocess.stdin.write accepts memoryview directly (zero-copy),
                # so we don't need .asstring() or .tobytes().
                bits = image.constBits()

                # Safety check: Ensure the image size matches expectation
                # (QImage sometimes adds padding bytes at the end of lines, though rarely for RGBA8888)
                expected_bytes = self.rec_width * self.rec_height * 4

                if image.sizeInBytes() == expected_bytes:
                    # Fast path: write buffer directly
                    self.ffmpeg_process.stdin.write(bits)
                else:
                    # Safe path: If there's padding, slice or copy to ensure exact size
                    # .tobytes() creates a clean copy of the data
                    self.ffmpeg_process.stdin.write(bits.tobytes()[:expected_bytes])

            except BrokenPipeError:
                # FFmpeg crashed or finished
                self.video_record_stop()
            except Exception as e:
                logger.error(f"Frame write error: {e}")
                error(
                    self,
                    "Error: Cannot continue to record video",
                    informative="Exception raised while recording video. See details",
                    detail=str(e),
                )
                self.video_record_stop()

    @Slot()
    def video_record_stop(self):
        self.recording_timer.stop()
        if self.ffmpeg_process:
            if self.ffmpeg_process.poll() is None:
                self.ffmpeg_process.stdin.close()
                self.ffmpeg_process.wait()
            self.ffmpeg_process = None

        self.record_toggle_button.setStyleSheet("")
        self.record_toggle_button.setChecked(False)
        self.restore_camera_state()

        self._show_media_capture_dialog("Video", self.recording_file_path)

    def _show_media_capture_dialog(self, name: str, save_path: str):
        """Handle a media capture dialog

        name [str]: Video or Image captured
        save_path [str]: Path to save the captured image / video

        """

        if name.lower() not in MediaType.get_media_types():
            error_msg = f"Provide one of these media types: {", ".join(MediaType.get_media_types())}. Got {name}"
            raise ValueError(error_msg)

        # Convert local path to a valid URL (handles Windows backslashes automatically)
        file_url = QUrl.fromLocalFile(save_path).toString()

        formatted_message = (
            f"File saved to:<br>"
            f"<a href='{file_url}' style='color: #0078d7;'>{save_path}</a><br><br>"
            f"Click on link to open file. Press ok to exit..."
        )

        ## Publish message that media has been captured
        media_capture_message = MediaCaptureMessageModel(
            path=Path(save_path),
            type=name.lower(),
        )

        publish_message(
            topic=DEVICE_VIEWER_MEDIA_CAPTURED,
            message=media_capture_message.model_dump_json(),
        )

        if self.show_media_capture_dialog:

            information(
                None,
                formatted_message,
                title=f"{name.title()} Captured",
            )

        logger.critical(f"Saved {name} media to {save_path}.")

        return True

from pathlib import Path

from PySide6.QtCore import (
    Signal,
    Slot,
    QTimer,
    QStandardPaths,
)
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaCaptureSession, QCamera, QMediaDevices, QCameraDevice
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QComboBox,
    QLabel,
    QSizePolicy,
    QApplication,
)

from apptools.preferences.api import Preferences

from microdrop_application.dialogs.pyface_wrapper import error, warning, YES, OK
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.v4l2_fps_getter import get_video_inputs, LinuxCameraDeviceContainer
from protocol_grid.consts import DEVICE_VIEWER_RECORDING_STATE

from device_viewer.views.camera_control_view.preferences import CameraPreferences
from microdrop_style.helpers import get_complete_stylesheet, is_dark_mode
from microdrop_utils.datetime_helpers import get_current_utc_datetime
from .utils import _cache_media_capture, _show_media_capture_dialog
from ..electrode_view.electrode_scene import ElectrodeScene
from ...default_settings import video_key

from ...utils.camera import (
    VideoRecorder,
    get_transformed_frame,
    ImageSaver,
)
from ...models.media_capture_model import MediaType

from logger.logger_service import get_logger
logger = get_logger(__name__)

class CameraControlWidget(QWidget):

    # Signals
    camera_active_signal = Signal(bool)
    screen_capture_signal = Signal(object)
    screen_recording_signal = Signal(object)

    def __init__(
        self,
        model,
        video_item: QGraphicsVideoItem,
        scene: ElectrodeScene,
        preferences: Preferences,
    ):
        super().__init__()
        self.model = model
        self.video_item = video_item
        self.scene = scene
        self.preferences = CameraPreferences(preferences=preferences)

        self.preferences.observe(
            self._preferred_video_format_change, "preferred_video_format"
        )
        self.preferences.observe(
            self._preferred_video_format_change, "strict_video_format"
        )

        self.session = QMediaCaptureSession()
        self.camera = None
        # Lookup dict mapping camera description -> LinuxCameraDeviceContainer.
        # Kept separate from combo box userData because shiboken cannot serialize
        # plain Python objects as QVariant — only Qt types (QCameraDevice) are safe
        # to store as combo box userData.
        self._linux_device_containers = {}
        self.last_camera_state = False
        self.available_cameras = None
        self.available_formats = None
        self.show_media_capture_dialog_for_video = True

        self.scene.addItem(self.video_item)
        self.session.setVideoOutput(self.video_item)

        # 1. Initialize Recorder
        self.recorder = VideoRecorder(self.video_item)
        self.recorder.error_occurred.connect(self.handle_recording_error)
        self.recorder.recording_stopped.connect(self.handle_recording_stopped)
        self.recording_file_path = None
        self._camera_state_pre_recording = None

        # Signal connectors
        self.camera_active_signal.connect(self.on_camera_active)
        self.screen_capture_signal.connect(self.capture_button_handler)
        self.screen_recording_signal.connect(self.on_recording_active)

        # UI Initialization
        self._init_ui()

        # Check initial camera state
        self.initialize_camera_list()
        self.check_initial_camera_state()

    def _init_ui(self):
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

        # Buttons
        self.button_align = QPushButton("view_in_ar")
        self.button_align.setToolTip("Align Camera Perspective")

        self.button_reset = QPushButton("reset_focus")
        self.button_reset.setToolTip("Reset Camera Perspective")

        self.camera_refresh_button = QPushButton("flip_camera_ios")
        self.camera_refresh_button.setToolTip("Refresh Camera List")

        self.record_toggle_button = QPushButton("album")
        self.record_toggle_button.setToolTip("Start Recording Video")
        self.record_toggle_button.setCheckable(True)

        self.capture_image_button = QPushButton("camera")
        self.capture_image_button.setToolTip("Capture Image")

        # Rotate camera option
        self.rotate_camera_button = QPushButton("cameraswitch")
        self.rotate_camera_button.setToolTip("Rotate Camera")
        self.rotate_camera_button.clicked.connect(
            lambda: self.scene.interaction_service.handle_rotate_camera()
        )

        # Rotate device option
        self.rotate_device_button = QPushButton("rotate_90_degrees_cw")
        self.rotate_device_button.setToolTip("Rotate Device")
        self.rotate_device_button.clicked.connect(
            lambda: self.scene.interaction_service.handle_rotate_device()
        )

        # Camera toggle
        self.camera_toggle_button = QPushButton("videocam_off")
        self.camera_toggle_button.setToolTip("Camera Off")
        self.camera_toggle_button.setCheckable(True)

        # Layouts
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.capture_image_button)
        top_layout.addWidget(self.camera_toggle_button)
        top_layout.addWidget(self.camera_refresh_button)
        top_layout.addWidget(self.rotate_camera_button)

        bottom_layout = QHBoxLayout()
        for btn in [self.record_toggle_button, self.button_align]:
            btn.setCheckable(True)
            bottom_layout.addWidget(btn)
        bottom_layout.addWidget(self.button_reset)
        bottom_layout.addWidget(self.rotate_device_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(self.camera_select_layout)
        main_layout.addLayout(self.resolution_select_layout)
        main_layout.addLayout(top_layout)
        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.sync_buttons_and_label()
        QApplication.styleHints().colorSchemeChanged.connect(
            self.sync_buttons_and_label
        )

        # Connections
        self.camera_toggle_button.clicked.connect(self.toggle_camera)
        self.button_align.clicked.connect(self.toggle_align_camera_mode)
        self.button_reset.clicked.connect(self.reset)
        self.capture_image_button.clicked.connect(self.capture_button_handler)
        self.record_toggle_button.clicked.connect(self.toggle_recording)
        self.camera_refresh_button.clicked.connect(self.initialize_camera_list)
        self.model.observe(self.on_mode_changed, "mode")
        self.combo_cameras.currentIndexChanged.connect(self.on_camera_changed)
        self.combo_resolutions.currentIndexChanged.connect(self.on_resolution_changed)

    # ... [Existing Camera Management Methods (populate_resolutions, etc.) remain unchanged] ...

    @staticmethod
    def _is_ir_camera_name(camera_name) -> bool:
        return bool(camera_name) and ("ir" in str(camera_name).lower())

    def _preferred_video_format_change(self, event):
        strict_flag = "strictly" if self.preferences.strict_video_format else ""
        logger.critical(
            f"Preferred video format changed to: {self.preferences.preferred_video_format} {strict_flag}"
        )
        self.populate_resolutions()

    def turn_on_camera(self):
        logger.info("Turning camera on")
        if not self.camera.isActive():
            self.camera.start()
            self.camera_toggle_button.setText("videocam")
            self.camera_toggle_button.setToolTip("Camera On")
            self.camera_toggle_button.setChecked(True)
            self.preferences.camera_state = True

    def turn_off_camera(self):
        logger.info("Turning camera off")
        if self.camera.isActive():
            self.camera.stop()
            self.camera_toggle_button.setText("videocam_off")
            self.camera_toggle_button.setToolTip("Camera Off")
            self.camera_toggle_button.setChecked(False)
            self.preferences.camera_state = False

    def toggle_camera(self):
        choice = OK
        if self.recorder.is_recording:
            choice = warning(
                None,
                title="Recording Session Active Warning",
                message="Are you sure you want to shut off the camera while recording?",
            )

        if choice in (OK, YES):
            self.turn_off_camera() if self.camera.isActive() else self.turn_on_camera()
        else:
            # Revert the button's checked state since Qt auto-toggles it on click
            self.camera_toggle_button.setChecked(self.camera.isActive())

        # keep the camera toggled button in sync with the alpha map.
        self.model.set_visible(video_key, self.camera.isActive())

    def check_initial_camera_state(self):
        if self.camera and self.camera.isActive():
            self.camera_toggle_button.setText("videocam")
            self.camera_toggle_button.setToolTip("Camera On")
            self.camera_toggle_button.setChecked(True)
        else:
            self.camera_toggle_button.setText("videocam_off")
            self.camera_toggle_button.setToolTip("Camera Off")
            self.camera_toggle_button.setChecked(False)

    def toggle_align_camera_mode(self):
        if self.model.mode == "camera-edit" or (
            self.model.mode != "camera-edit" and self.can_enter_edit_mode()
        ):
            self.model.flip_mode_activation("camera-edit")
        else:
            self.model.flip_mode_activation("camera-place")

    def can_enter_edit_mode(self) -> bool:
        return self.model.camera_perspective.perspective_transformation_possible()

    @Slot(bool)
    def on_camera_active(self, active):
        if active:
            self.turn_on_camera()
        else:
            self.turn_off_camera()

    def on_mode_changed(self, event):
        self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        if self.model.mode == "camera-place":
            self.button_align.setChecked(True)
            self.button_align.setStyleSheet(
                get_complete_stylesheet("dark" if is_dark_mode() else "light")
            )
        elif self.model.mode == "camera-edit":
            self.button_align.setChecked(True)
            self.button_align.setStyleSheet("background-color: green;")
        else:
            self.button_align.setChecked(False)
            self.button_align.setStyleSheet(
                get_complete_stylesheet("dark" if is_dark_mode() else "light")
            )

    def reset(self):
        self.model.camera_perspective.reset()
        if self.model.mode == "camera-edit":
            self.model.mode = "camera-place"

    def _get_camera_from_available_cameras(self, selected_device):
        """Create a QCamera from either a LinuxCameraDeviceContainer or QCameraDevice.

        On Linux, cameras are wrapped in LinuxCameraDeviceContainer to carry
        V4L2 metadata (fps, device path). This method unwraps the container
        to get the underlying QCameraDevice before constructing the QCamera.
        """
        _device = None

        if isinstance(selected_device, LinuxCameraDeviceContainer):
            _device = selected_device.camera_device

        elif isinstance(selected_device, QCameraDevice):
            _device = selected_device

        if isinstance(_device, QCameraDevice):
            return QCamera(selected_device)

        else:
            logger.warning("Failed to create camera. Need to get camera from available devices")
            return None

    def _get_camera_description(self, selected_device):
        """Return a human-readable identifier for a camera device.

        LinuxCameraDeviceContainer returns the /dev/videoN path (unique on Linux),
        while QCameraDevice returns the Qt-provided description string.
        """
        if isinstance(selected_device, LinuxCameraDeviceContainer):
            return selected_device.device_path

        elif isinstance(selected_device, QCameraDevice):
            return selected_device.description()

    def initialize_camera_list(self):
        preferences_camera = self.preferences.selected_camera
        old_camera_name = (
            preferences_camera
            if preferences_camera
            else self.combo_cameras.currentText()
        )

        _available_cameras = get_video_inputs()
        self.combo_cameras.clear()
        self.combo_cameras.blockSignals(True)
        self._linux_device_containers.clear()

        for camera in _available_cameras:
            description = self._get_camera_description(camera)
            if isinstance(camera, LinuxCameraDeviceContainer):
                # Store the container in a side dict for V4L2 fps lookups.
                # Only the underlying QCameraDevice goes into combo userData
                # (shiboken crashes on non-Qt types in QVariant).
                self._linux_device_containers[description] = camera
                self.combo_cameras.addItem(description, userData=camera.camera_device)
            else:
                self.combo_cameras.addItem(description, userData=camera)

        # account for no camera
        _available_cameras.append(None)
        self.combo_cameras.addItem("<No Camera>", userData=None)

        self.combo_cameras.blockSignals(False)

        self.combo_cameras.setCurrentIndex(-1)

        if old_camera_name:
            for i, camera in enumerate(_available_cameras):
                if camera and self._get_camera_description(camera) == old_camera_name:
                    self.combo_cameras.setCurrentIndex(i)
                    return

            # Preferred camera not found — clear stale resolution since it
            # belonged to the missing camera, then fall back.
            logger.warning(
                f"Preferred camera '{old_camera_name}' not found. "
                f"Falling back to first available camera."
            )
            self.preferences.resolution = ""

        self.combo_cameras.setCurrentIndex(0)

    def _disable_camera_buttons(self, disable):
        self.camera_toggle_button.setDisabled(disable)
        self.record_toggle_button.setDisabled(disable)
        self.capture_image_button.setDisabled(disable)
        self.rotate_camera_button.setDisabled(disable)

    def on_camera_changed(self, index):

        if self.combo_cameras.count() == 0 or index < 0:
            self._disable_camera_buttons(True)
            return

        camera = self.combo_cameras.itemData(index)

        was_running = False
        if self.camera and self.camera.isActive():
            self.turn_off_camera()
            was_running = True

        if camera:
            self.camera = self._get_camera_from_available_cameras(camera)
            self.session.setCamera(self.camera)
            self.preferences.selected_camera = self._get_camera_description(camera)
            self.video_item.setVisible(True)
            self._disable_camera_buttons(False)

        else:
            self._disable_camera_buttons(True)

        self.populate_resolutions()

        if was_running and camera:
            self.turn_on_camera()

    def populate_resolutions(self, allow_strict_mode=True):
        """Populate the resolution combo box from the current camera's formats.

        Sorts formats by resolution (descending), preferred pixel format, and
        frame rate.  In strict mode only formats matching the preferred pixel
        format are shown; if none match, the method recurses once with strict
        mode disabled.

        After populating, tries to restore the saved resolution preference.
        Falls back to the middle entry when the saved value is unavailable.
        """
        self.combo_resolutions.blockSignals(True)
        self.combo_resolutions.clear()

        # -- 1. Collect and sort available formats --------------------------------
        formats = self.camera.cameraDevice().videoFormats()
        preferred_fmt = self.preferences.preferred_video_format.upper()

        def format_sort_key(fmt):
            res = fmt.resolution()
            fmt_name = str(fmt.pixelFormat()).upper()
            return (
                res.width(),
                res.height(),
                preferred_fmt in fmt_name,
                fmt.maxFrameRate(),
            )

        formats.sort(key=format_sort_key, reverse=True)

        # -- 2. Build combo-box entries (one per unique resolution) ----------------
        strict_mode = self.preferences.strict_video_format and allow_strict_mode
        seen_resolutions = set()

        for fmt in formats:
            w, h = fmt.resolution().width(), fmt.resolution().height()
            fmt_name = str(fmt.pixelFormat()).upper()

            # In strict mode, skip formats that don't match the preference
            if strict_mode and preferred_fmt not in fmt_name:
                continue

            # De-duplicate by resolution — the sort ensures the best pixel
            # format / frame-rate combo comes first for each resolution.
            if (w, h) in seen_resolutions:
                continue
            seen_resolutions.add((w, h))

            fps = fmt.maxFrameRate()
            pix_name = str(fmt.pixelFormat()).split(".")[-1].replace("Format_", "")
            label = f"{w}x{h} [{pix_name}] @ {fps:.0f} fps"
            self.combo_resolutions.addItem(label, userData=fmt)

        self.combo_resolutions.blockSignals(False)

        # -- 3. Select a resolution -----------------------------------------------
        if seen_resolutions:
            self._restore_or_fallback_resolution(seen_resolutions)
        elif self.preferences.strict_video_format:
            # No formats survived strict filtering — retry without it
            warning_message = f"Preferred format {self.preferences.preferred_video_format} not supported."
            logger.warning(warning_message)
            if not self._is_ir_camera_name(self.preferences.selected_camera):
                warning(None, warning_message)
            self.populate_resolutions(allow_strict_mode=False)
            return

        # Ensure the model always has a resolution set (e.g. when the combo
        # index didn't change and on_resolution_changed was never triggered).
        if not self.model.camera_perspective.camera_resolution:
            self.on_resolution_changed(self.combo_resolutions.currentIndex())

    def _restore_or_fallback_resolution(self, seen_resolutions):
        """Try to select the saved resolution; fall back to the middle entry."""
        saved_resolution = self.preferences.resolution

        # Look for the saved resolution in the combo box
        if saved_resolution:
            for i in range(self.combo_resolutions.count()):
                if self.combo_resolutions.itemText(i) == saved_resolution:
                    self.combo_resolutions.setCurrentIndex(i)
                    return

            logger.warning(
                f"Saved resolution '{saved_resolution}' not available. "
                f"Falling back to default (middle resolution)."
            )

        # No saved preference or it wasn't found — pick the middle resolution
        fallback_index = len(seen_resolutions) // 2
        self.combo_resolutions.setCurrentIndex(fallback_index)

    def on_resolution_changed(self, index):
        if self.combo_resolutions.count() == 0 or index < 0:
            return
        resolution = self.combo_resolutions.itemData(index)
        was_running = self.camera.isActive()

        if was_running:
            self.camera.stop()
            QApplication.processEvents()

        self.camera.setCameraFormat(resolution)
        self.preferences.resolution = self.combo_resolutions.itemText(index)
        self.model.camera_perspective.camera_resolution = (
            resolution.resolution().width(),
            resolution.resolution().height(),
        )

        if was_running:
            self.camera.start()

    def _capture_image_routine(self, capture_data=None):
        # 3. Capture Pixels (Must happen on UI thread)
        image = self.get_screen_shot()

        if not image or image.isNull():
            return

        directory, step_description, step_id, show_dialog = None, None, None, True
        if isinstance(capture_data, dict):
            directory = capture_data.get("directory")
            step_description = capture_data.get("step_description")
            step_id = capture_data.get("step_id")
            show_dialog = capture_data.get("show_dialog", True)

        # 4. Generate Path
        filename = self._generate_capture_filename(step_description, step_id)
        if directory:
            save_path = Path(directory) / "captures" / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            save_path = (
                Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation))
                / filename
            )

        worker = ImageSaver(image.copy(), str(save_path))

        def _post_image_capture():
            _cache_media_capture(MediaType.IMAGE, str(save_path))
            if show_dialog:
                _show_media_capture_dialog(MediaType.IMAGE, str(save_path))

        worker.signals.save_complete.connect(_post_image_capture)

        # FIXME: this could be run in a separate thread for more performance if needed. Its a QRunnable...
        worker.run()

    def _capture_image_and_close(self, capture_data):
        self._capture_image_routine(capture_data)
        self.toggle_camera()

    @Slot()
    def capture_button_handler(self, capture_data=None):

        if self.camera.isActive():
            self._capture_image_routine(capture_data)

        else:
            self.toggle_camera()
            QTimer.singleShot(1000, lambda: self._capture_image_and_close(capture_data))

    def _generate_media_filename(
        self, step_description=None, step_id=None, file_extension=".png"
    ):
        timestamp = get_current_utc_datetime()
        if step_description and step_id:
            clean_desc = "".join(
                c for c in step_description if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()
            clean_desc = clean_desc.replace(" ", "_")
            return f"{clean_desc}_{step_id}_{timestamp}{file_extension}"
        elif step_id:
            return f"step_{step_id}_{timestamp}{file_extension}"
        else:
            return f"captured_media_{timestamp}{file_extension}"

    def _generate_capture_filename(self, step_description=None, step_id=None):
        return self._generate_media_filename(step_description, step_id, ".png")

    def _generate_recording_filename(self, step_description=None, step_id=None):
        return self._generate_media_filename(step_description, step_id, ".mkv")

    def on_recording_active(self, recording_data):
        if isinstance(recording_data, dict):
            action = recording_data.get("action", "").lower()
            if action == "start":
                self.video_record_start(
                    recording_data.get("directory"),
                    recording_data.get("step_description"),
                    recording_data.get("step_id"),
                    recording_data.get("show_dialog", True),
                )
                self.record_toggle_button.setChecked(True)
            elif action == "stop":
                self.video_record_stop()
                self.record_toggle_button.setChecked(False)
        else:
            logger.error(f"Invalid recording data: {recording_data}")

    # --- Transformation Logic (For Single Screenshots - Main Thread) ---
    def get_screen_shot(self):

        if self.recorder.is_recording:
            if self.recorder.current_image:
                return self.recorder.current_image

        frame = self.video_item.videoSink().videoFrame()

        # 1. Image and Scene Data
        source_image = frame.toImage()

        if source_image.isNull():
            return QImage()

        mapped_rect = self.video_item.sceneBoundingRect()
        target_rect = self.video_item.boundingRect()

        transform = self.video_item.transform()

        target_resolution_size = self.combo_resolutions.currentData().resolution()
        target_resolution_w, target_resolution_h = (
            target_resolution_size.width(),
            target_resolution_size.height(),
        )

        return get_transformed_frame(
            source_image,
            mapped_rect,
            target_rect,
            transform,
            (target_resolution_w, target_resolution_h),
        )

    # --- Video Recording (Background Thread) ---

    @Slot()
    def toggle_recording(self):
        if self.recorder.is_recording:
            self.video_record_stop()
        else:
            self.video_record_start()

    @Slot()
    def video_record_start(
        self, directory=None, step_description=None, step_id=None, show_dialog=True
    ):
        logger.info("Starting video recorder...")
        if not self.camera.isActive():
            self.toggle_camera()
            self._camera_state_pre_recording = False ## Flag only used for video recording management

        else:
            self._camera_state_pre_recording = True

        filename = self._generate_recording_filename(step_description, step_id)
        if directory:
            path = Path(directory) / "recordings" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            _recording_file_path = str(path)
        else:
            _recording_file_path = str(
                Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation))
                / filename
            )

        self.show_media_capture_dialog_for_video = show_dialog

        _current_fmt = self.combo_resolutions.currentData()
        _resolution = (
            _current_fmt.resolution().width(),
            _current_fmt.resolution().height(),
        )

        self.recorder.start(
            _recording_file_path, _resolution, _current_fmt.maxFrameRate()
        )
        publish_message(topic=DEVICE_VIEWER_RECORDING_STATE, message="true")

    def video_record_stop(self):
        logger.info("Stopping video recorder...")
        self.recorder.stop()

    @Slot(str)
    def handle_recording_error(self, error_msg):
        logger.error(f"Recording Error: {error_msg}")
        publish_message(topic=DEVICE_VIEWER_RECORDING_STATE, message="false")
        error(
            self,
            "<b>Error</b>: Cannot continue to record video<br><br>Exception raised while recording video.",
            detail=error_msg,
        )
        self.video_record_stop()

    @Slot(str)
    def handle_recording_stopped(self, recording_output_path):
        publish_message(topic=DEVICE_VIEWER_RECORDING_STATE, message="false")
        if not self._camera_state_pre_recording:
            # turn off camera if we need to
            if self.camera.isActive():
                self.toggle_camera()

        # Show Result
        if recording_output_path and self.show_media_capture_dialog_for_video:
            _show_media_capture_dialog(
                MediaType.VIDEO, recording_output_path
            )

import shutil
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QRectF,
    QObject,
    QThread,
    Signal,
    Slot,
    QTimer,
    QStandardPaths,
    QUrl,
    QThreadPool,
)
from PySide6.QtGui import QImage, QPainter, QTransform
from PySide6.QtMultimedia import QVideoFrame, QMediaCaptureSession, QCamera, QMediaDevices
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
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

from apptools.preferences.api import Preferences
from microdrop_application.dialogs.pyface_wrapper import error, warning, success

from device_viewer.views.camera_control_view.preferences import CameraPreferences
from logger.logger_service import get_logger
from microdrop_style.helpers import get_complete_stylesheet, is_dark_mode
from microdrop_utils.datetime_helpers import get_current_utc_datetime
from ...utils.camera import (
    VideoRecorder,
    VideoRecorderWorker,
    get_transformed_frame,
    ImageSaver,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ...models.media_capture_model import MediaCaptureMessageModel, MediaType
from protocol_grid.consts import DEVICE_VIEWER_MEDIA_CAPTURED

logger = get_logger(__name__)

class CameraControlWidget(QWidget):

    # Signals
    camera_active_signal = Signal(bool)
    screen_capture_signal = Signal(object)
    screen_recording_signal = Signal(object)

    # Signal to send data to the background worker thread
    send_frame_to_worker = Signal(object, QRectF, QRectF, QTransform)

    def __init__(
            self,
            model,
            video_item: QGraphicsVideoItem,
            scene: QGraphicsScene,
            preferences: Preferences,
    ):
        super().__init__()
        self.camera_was_off_before_action = None
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
        self.available_cameras = None
        self.available_formats = None
        self.show_media_capture_dialog = True

        self.scene.addItem(self.video_item)
        self.session.setVideoOutput(self.video_item)

        self.recording_timer = QTimer()
        self.recording_file_path = None
        self._is_recording = False
        self.recorder = VideoRecorder()

        # Threading components
        self.thread = None
        self.worker = None

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
        self.rotate_camera_button.clicked.connect(lambda: self.scene.interaction_service.handle_rotate_camera())

        # Rotate device option
        self.rotate_device_button = QPushButton("rotate_90_degrees_cw")
        self.rotate_device_button.setToolTip("Rotate Device")
        self.rotate_device_button.clicked.connect(lambda: self.scene.interaction_service.handle_rotate_device())

        # Camera toggle
        self.camera_toggle_button = QPushButton("videocam_off")
        self.camera_toggle_button.setToolTip("Camera Off")
        self.camera_toggle_button.setCheckable(True)
        self.is_camera_on = False
        self.camera_was_off_before_action = False

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

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.sync_buttons_and_label()
        QApplication.styleHints().colorSchemeChanged.connect(self.sync_buttons_and_label)

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
        logger.critical(f"Preferred video format changed to: {self.preferences.preferred_video_format} {strict_flag}")
        self.populate_resolutions()

    def turn_on_camera(self):
        logger.info("Turning camera on")
        if self.camera:
            self.camera.start()
            self.camera_toggle_button.setText("videocam")
            self.camera_toggle_button.setToolTip("Camera On")
            self.camera_toggle_button.setChecked(True)
            self.is_camera_on = True
            self.preferences.camera_state = True

    def turn_off_camera(self):
        logger.info("Turning camera off")
        if self.camera:
            self.camera.stop()
            self.camera_toggle_button.setText("videocam_off")
            self.camera_toggle_button.setToolTip("Camera Off")
            self.camera_toggle_button.setChecked(False)
            self.is_camera_on = False
            self.preferences.camera_state = False

    def toggle_camera(self):
        self.turn_off_camera() if self.is_camera_on else self.turn_on_camera()

    def toggle_align_camera_mode(self):
        if self.model.mode == "camera-edit" or (self.model.mode != "camera-edit" and self.can_enter_edit_mode()):
            self.model.flip_mode_activation("camera-edit")
        else:
            self.model.flip_mode_activation("camera-place")

    def can_enter_edit_mode(self) -> bool:
        return self.model.camera_perspective.perspective_transformation_possible()

    @Slot(bool)
    def on_camera_active(self, active):
        if active:
            self.turn_on_camera()
        else: self.turn_off_camera()

    def on_mode_changed(self, event):
        self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        if self.model.mode == "camera-place":
            self.button_align.setChecked(True)
            self.button_align.setStyleSheet(get_complete_stylesheet("dark" if is_dark_mode() else "light"))
        elif self.model.mode == "camera-edit":
            self.button_align.setChecked(True)
            self.button_align.setStyleSheet("background-color: green;")
        else:
            self.button_align.setChecked(False)
            self.button_align.setStyleSheet(get_complete_stylesheet("dark" if is_dark_mode() else "light"))

    def reset(self):
        self.model.camera_perspective.reset()
        if self.model.mode == "camera-edit":
            self.model.mode = "camera-place"

    def initialize_camera_list(self):
        preferences_camera = self.preferences.selected_camera
        old_camera_name = preferences_camera if preferences_camera else self.combo_cameras.currentText()

        self.available_cameras = QMediaDevices.videoInputs()
        self.combo_cameras.clear()
        self.available_cameras.append(None)

        self.combo_cameras.blockSignals(True)
        for camera in self.available_cameras:
            self.combo_cameras.addItem(camera.description() if camera else "<No Camera>")
        self.combo_cameras.blockSignals(False)

        self.combo_cameras.setCurrentIndex(-1)
        if old_camera_name:
            for i, camera in enumerate(self.available_cameras):
                if camera and camera.description() == old_camera_name:
                    self.combo_cameras.setCurrentIndex(i)
                    return
        self.combo_cameras.setCurrentIndex(0)

    def on_camera_changed(self, index):
        if index < 0 or index >= len(self.available_cameras): return
        elif not self.available_cameras[index]: return

        was_running = False
        if self.camera and self.camera.isActive():
            self.camera.stop()
            was_running = True

        self.video_item.setVisible(True)
        self.camera = QCamera(self.available_cameras[index])
        self.session.setCamera(self.camera)
        self.preferences.selected_camera = self.available_cameras[index].description()
        self.populate_resolutions()
        if was_running: self.camera.start()

    def populate_resolutions(self, allow_strict_mode=True):
        self.combo_resolutions.blockSignals(True)
        self.combo_resolutions.clear()
        formats = self.camera.cameraDevice().videoFormats()

        def format_sort_key(fmt):
            res = fmt.resolution()
            fmt_name = str(fmt.pixelFormat()).upper()
            return (res.width(), res.height(), self.preferences.preferred_video_format.upper() in fmt_name, fmt.maxFrameRate())

        formats.sort(key=format_sort_key, reverse=True)
        seen_resolutions = set()
        _strict_mode = self.preferences.strict_video_format and allow_strict_mode

        for fmt in formats:
            w, h = fmt.resolution().width(), fmt.resolution().height()
            res_key = (w, h)
            fmt_name = str(fmt.pixelFormat()).upper()

            if (_strict_mode and self.preferences.preferred_video_format.upper() in fmt_name) or not _strict_mode:
                if res_key not in seen_resolutions:
                    seen_resolutions.add(res_key)
                    fps = fmt.maxFrameRate()
                    pix_name = str(fmt.pixelFormat()).split(".")[-1].replace("Format_", "")
                    label = f"{w}x{h} [{pix_name}] @ {fps:.0f} fps"
                    self.combo_resolutions.addItem(label, userData=fmt)

        self.combo_resolutions.blockSignals(False)
        if len(seen_resolutions) > 0:
            if not self.preferences.resolution or not _strict_mode:
                if len(seen_resolutions) // 2 != self.combo_resolutions.currentIndex():
                    self.combo_resolutions.setCurrentIndex(len(seen_resolutions) // 2)
                else:
                    self.on_resolution_changed(self.combo_resolutions.currentIndex())
            else:
                for i in range(self.combo_resolutions.count()):
                    if self.preferences.resolution == self.combo_resolutions.itemText(i):
                        self.combo_resolutions.setCurrentIndex(i)
        elif self.preferences.strict_video_format:
            warning_message = f"Preferred format {self.preferences.preferred_video_format} not supported."
            logger.warning(warning_message)
            if not self._is_ir_camera_name(self.preferences.selected_camera):
                warning(None, warning_message)
            self.populate_resolutions(allow_strict_mode=False)

    def on_resolution_changed(self, index):
        if self.combo_resolutions.count() == 0 or index < 0: return
        resolution = self.combo_resolutions.itemData(index)
        was_running = self.camera.isActive()
        if was_running:
            self.camera.stop()
            QApplication.processEvents()
        self.camera.setCameraFormat(resolution)
        self.preferences.resolution = self.combo_resolutions.itemText(index)
        self.model.camera_perspective.camera_resolution = (resolution.resolution().width(), resolution.resolution().height())
        if was_running: self.camera.start()

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
            save_path = Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)) / filename

        # 5. The Threaded Strategy
        # We pass the copy of the image to the worker so the UI thread is free immediately
        worker = ImageSaver(image.copy(), str(save_path), "Image")

        # This signal is the key. It 'decouples' the saving from the UI.
        # The background thread emits this, and the UI thread picks it up
        # as a separate event later.
        worker.signals.save_complete.connect(
            lambda name, path: self._show_media_capture_dialog(name, path, show_media_capture_dialog=show_dialog)
        )

        # FIXME: this could be run in a separate thread for more performance if needed. Its a QRunnable...
        worker.run()

        # 6. Immediate cleanup so recording/UI flow isn't interrupted
        if not self._is_recording and self.camera_was_off_before_action:
            self.restore_camera_state()

    @Slot()
    def capture_button_handler(self, capture_data=None):
        self.ensure_camera_on()
        if self.camera_was_off_before_action:
            QTimer.singleShot(1000, lambda: self._capture_image_routine(capture_data))
        else:
            self._capture_image_routine(capture_data)

    def ensure_camera_on(self):
        if not self.is_camera_on:
            self.camera_was_off_before_action = True
            self.turn_on_camera()

    def restore_camera_state(self):
        if self.camera_was_off_before_action:
            self.turn_off_camera()
            self.camera_was_off_before_action = False

    def check_initial_camera_state(self):
        if self.camera and self.camera.isActive():
            self.is_camera_on = True
            self.camera_toggle_button.setText("videocam")
            self.camera_toggle_button.setToolTip("Camera On")
            self.camera_toggle_button.setChecked(True)
        else:
            self.is_camera_on = False
            self.camera_toggle_button.setText("videocam_off")
            self.camera_toggle_button.setToolTip("Camera Off")
            self.camera_toggle_button.setChecked(False)

    def _generate_media_filename(self, step_description=None, step_id=None, file_extension=".png"):
        timestamp = get_current_utc_datetime()
        if step_description and step_id:
            clean_desc = "".join(c for c in step_description if c.isalnum() or c in (" ", "-", "_")).rstrip()
            clean_desc = clean_desc.replace(" ", "_")
            return f"{clean_desc}_{step_id}_{timestamp}{file_extension}"
        elif step_id:
            return f"step_{step_id}_{timestamp}{file_extension}"
        else:
            return f"captured_image_{timestamp}{file_extension}"

    def _generate_capture_filename(self, step_description=None, step_id=None):
        return self._generate_media_filename(step_description, step_id, ".png")

    def _generate_recording_filename(self, step_description=None, step_id=None):
        return self._generate_media_filename(step_description, step_id, ".mp4")

    def on_recording_active(self, recording_data):
        if isinstance(recording_data, dict):
            action = recording_data.get("action", "").lower()
            if action == "start":
                self.video_record_start(
                    recording_data.get("directory"),
                    recording_data.get("step_description"),
                    recording_data.get("step_id"),
                    recording_data.get("show_dialog", True)
                )
            elif action == "stop":
                self.video_record_stop()
        else:
            logger.error(f"Invalid recording data: {recording_data}")

    # --- Transformation Logic (For Single Screenshots - Main Thread) ---
    def get_screen_shot(self):

        if self._is_recording:
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
        target_resolution_w, target_resolution_h = target_resolution_size.width(), target_resolution_size.height()

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
        if self._is_recording:
            self.video_record_stop()
        else:
            self.video_record_start()

    @Slot()
    def video_record_start(self, directory=None, step_description=None, step_id=None, show_dialog=True):
        if self._is_recording:
            return

        if not shutil.which("ffmpeg"):
            logger.error("FFmpeg not found.")
            error(self, "Error: Cannot start to record video", informative="FFmpeg not found.")
            return

        self.ensure_camera_on()

        filename = self._generate_recording_filename(step_description, step_id)
        if directory:
            path = Path(directory) / "recordings" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            self.recording_file_path = str(path)
        else:
            self.recording_file_path = str(Path(QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)) / filename)

        self.show_media_capture_dialog = show_dialog

        current_fmt = self.combo_resolutions.currentData()
        resolution = (current_fmt.resolution().width(), current_fmt.resolution().height())

        if self.recorder.start(self.recording_file_path, resolution, current_fmt.maxFrameRate()):

            # --- Initialize Worker Thread ---
            self.thread = QThread()
            self.worker = VideoRecorderWorker(
                self.recorder,
            )

            self.worker.moveToThread(self.thread)
            self.thread.finished.connect(self.worker.deleteLater)

            # Connect Signals
            self.send_frame_to_worker.connect(self.worker.process_frame)
            self.worker.error_occurred.connect(self.handle_recording_error)

            self.thread.start()
            self._is_recording = True

            # some settling time then start recording
            QTimer.singleShot(0, lambda: self.video_item.videoSink().videoFrameChanged.connect(self.video_record_frame_handler))


    @Slot()
    def video_record_frame_handler(self, frame=None):
        """
        LIGHTWEIGHT: Only captures state and emits signal to Worker.
        """
        if not self._is_recording:
            return
        # 1. Convert to Image (Main Thread - Fast)
        source_image = frame
        # Send to worker
        self.send_frame_to_worker.emit(
            source_image,
            self.video_item.sceneBoundingRect(),
            self.video_item.boundingRect(),
            self.video_item.transform(),
        )

    @Slot(str)
    def handle_recording_error(self, error_msg):
        logger.error(f"Recording Error: {error_msg}")
        error(
            self,
            "Error: Cannot continue to record video",
            informative="Exception raised while recording video.",
            detail=error_msg,
        )
        self.video_record_stop()

    @Slot()
    def video_record_stop(self):
        # 1. Stop feeding frames
        try:
            self.video_item.videoSink().videoFrameChanged.disconnect(self.video_record_frame_handler)
        except Exception:
            pass # Disconnect might fail if not connected

        # 3. Stop Recorder
        self.recorder.stop()
        self.worker.stop()

        # 4. UI Cleanup
        self.restore_camera_state()
        self._is_recording = False

        self.thread.quit()
        self.thread.terminate()

        self.record_toggle_button.setChecked(False)

        # 5. Show Result
        if self.recording_file_path:
            self._show_media_capture_dialog("Video", self.recording_file_path)

    def _show_media_capture_dialog(self, name: str, save_path: str, show_media_capture_dialog=None):
        if name.lower() not in MediaType.get_media_types():
            raise ValueError(f"Invalid media type: {name}")

        file_url = QUrl.fromLocalFile(save_path).toString()
        formatted_message = f"File saved to:<br><a href='{file_url}' style='color: #0078d7;'>{save_path}</a><br><br>"

        media_capture_message = MediaCaptureMessageModel(path=Path(save_path), type=name.lower())
        publish_message(topic=DEVICE_VIEWER_MEDIA_CAPTURED, message=media_capture_message.model_dump_json())

        if show_media_capture_dialog is None:
            show_media_capture_dialog = self.show_media_capture_dialog

        if show_media_capture_dialog:
            # Create a non-modal popup (doesn't block the rest of the UI)
            success(None, formatted_message, title=f"{name} Captured", modal=False, timeout=5000)

        logger.critical(f"Saved {name} media to {save_path}.")

        return True

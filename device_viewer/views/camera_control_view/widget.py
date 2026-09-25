# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera panel's view: buttons, source/format combos, provider feeds,
recorders and frame grabs. Decisions and publishing live in
CameraController, state in CameraModel; the QCamera/QMediaCaptureSession
pair lives in QtCameraDevice, owned here because it is Qt."""

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtCore import QThreadPool, QTimer, Signal, Slot
from pyface.qt.QtGui import QImage
from pyface.qt.QtMultimedia import QCameraFormat, QVideoSink
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem
from pyface.qt.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Microdrop package imports.
from device_viewer.views.camera_control_view.preferences import CameraPreferences
from microdrop_application.dialogs.pyface_wrapper import (
    OK,
    YES,
    disclaimer,
    error,
    warning,
)

# Microdrop style imports.
from microdrop_style.helpers import get_complete_stylesheet, is_dark_mode

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import MarqueeComboBox
from microdrop_utils.v4l2_fps_getter import (
    LinuxCameraDeviceContainer,
    get_video_inputs,
)

# Local imports.
from ...consts import MIN_RECORDING_FPS, RECORDER_BACKEND_FFMPEG
from ...controllers.camera_controller import CameraController
from ...default_settings import video_key
from ...models.camera import CameraModel
from ...models.media import MediaType
from ...utils.capture import ImageSaver, get_transformed_frame
from ...utils.recording.ffmpeg import RawFFMPEGVideoRecorder
from ...utils.recording.native import NativeVideoRecorder
from ..electrode_view.electrode_scene import ElectrodeScene
from .qt_camera_device import QtCameraDevice
from .utils import _show_media_capture_status_message

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class CameraControlWidget(QWidget):
    # Signals
    camera_active_signal = Signal(bool)
    screen_capture_signal = Signal(object)
    screen_recording_signal = Signal(object)

    #: A CameraControlsRequest dict, emitted by the dock pane's topic handler
    #: (a Dramatiq worker thread) and applied on the GUI thread.
    camera_controls_signal = Signal(object)

    def __init__(
        self,
        model,
        video_item: QGraphicsVideoItem,
        scene: ElectrodeScene,
        preferences: Preferences,
        status_bar_manager=None,
        source_providers=None,
    ):
        super().__init__()
        self.model = model
        self.video_item = video_item
        self.scene = scene
        self.preferences = CameraPreferences(preferences=preferences)
        # May be None at construction time — the dock pane re-pushes this
        # once the trait fires `task:window:status_bar_manager`.
        self.status_bar_manager = status_bar_manager

        self.preferences.observe(
            self._preferred_video_format_change, "preferred_video_format"
        )
        self.preferences.observe(
            self._preferred_video_format_change, "strict_video_format"
        )

        # Lookup dict mapping camera description -> LinuxCameraDeviceContainer.
        # Kept separate from combo box userData because shiboken cannot serialize
        # plain Python objects as QVariant — only Qt types (QCameraDevice) are safe
        # to store as combo box userData.
        self._linux_device_containers = {}
        # Extra camera sources from the CAMERA_SOURCES extension point.
        # A callable is resolved fresh on every camera-list refresh, so
        # contributions from hot-loaded plugin groups (which start AFTER
        # this widget is built) appear on the next refresh. Label ->
        # (provider, key); labels double as combo entries (only Qt types
        # are safe as combo userData, so providers ride a side dict).
        self.source_providers = source_providers
        self._provider_sources = {}
        self._active_feed = None
        self._feed_controls = None
        # In-flight ImageSaver workers, referenced so a pool worker (and its
        # signals QObject) cannot be garbage-collected before its completion
        # signal is delivered back to the GUI thread.
        self._pending_image_savers = set()

        self.scene.addItem(self.video_item)

        # The session delivers to its own sink at full camera rate; frames
        # are forwarded to the DISPLAY item capped at CAMERA_PREVIEW_MAX_FPS
        # (every frame under the electrodes is a full-scene composite, and
        # the preview doesn't need camera rate to be useful).
        self.camera_device = QtCameraDevice(
            video_item=self.video_item, sink=QVideoSink(self)
        )
        self.camera_model = CameraModel()
        self.controller = CameraController(
            model=self.camera_model,
            preferences=self.preferences,
            camera=self.camera_device,
            turn_camera_on=self.turn_on_camera,
        )

        # 1. Initialize Recorder. The backend (Qt MediaRecorder vs FFmpeg
        # process) and its encoding settings come from the camera
        # preferences; the recorder is rebuilt from them at every recording
        # start (see _build_recorder), so preference changes apply live.
        self.recorder = self._build_recorder()

        # Signal connectors
        self.camera_active_signal.connect(self.on_camera_active)
        self.screen_capture_signal.connect(self.capture_button_handler)
        self.screen_recording_signal.connect(self.on_recording_active)
        self.camera_controls_signal.connect(self.apply_camera_controls)

        # UI Initialization
        self._init_ui()

        # Check initial camera state
        self.initialize_camera_list()
        self.check_initial_camera_state()

    def _build_recorder(self, resolution=None, fps=None):
        """Recorder configured from the camera preferences. Both recorders
        share VideoRecorderBase, so the rest of the widget is agnostic.
        ``resolution``/``fps`` (known at recording start) select which
        per-resolution-class bitrate preference applies to the Qt/MKV
        recorder; at construction time they are unknown and the bitrate
        stays encoder-chosen."""

        if self.preferences.recorder_backend == RECORDER_BACKEND_FFMPEG:
            # Raw camera planes piped to an ffmpeg subprocess at full
            # camera rate (untouched by the preview frame cap thanks to
            # frame_sink=the session's own sink).
            logger.info(
                f"Recorder from preferences: FFmpeg process — "
                f"container={self.preferences.ffmpeg_container}, "
                f"codec={self.preferences.ffmpeg_video_codec}, "
                f"preset={self.preferences.ffmpeg_preset}, "
                f"crf={self.preferences.ffmpeg_crf}, "
                f"extra args={self.preferences.ffmpeg_extra_output_args!r}"
            )
            recorder = RawFFMPEGVideoRecorder(
                self.video_item,
                frame_sink=self.camera_device.sink,
                video_codec=self.preferences.ffmpeg_video_codec,
                preset=self.preferences.ffmpeg_preset,
                crf=self.preferences.ffmpeg_crf,
                extra_output_args=self.preferences.ffmpeg_extra_output_args,
            )
        else:
            # Qt's own QMediaRecorder: hardware-encoded, zero per-frame
            # Python work.
            video_bitrate = self.preferences.recording_bitrate_bps(resolution, fps)
            bitrate_description = (
                f"{video_bitrate:,} bps" if video_bitrate else "encoder default"
            )
            logger.info(
                f"Recorder from preferences: Qt MediaRecorder — "
                f"format={self.preferences.qt_video_format}, "
                f"codec={self.preferences.qt_video_codec}, "
                f"bitrate={bitrate_description}"
            )
            recorder = NativeVideoRecorder(
                session=self.camera_device.session,
                video_item=self.video_item,
                file_format=self.preferences.qt_video_format,
                video_codec=self.preferences.qt_video_codec,
                video_bitrate=video_bitrate,
            )

        recorder.error_occurred.connect(self.handle_recording_error)
        recorder.recording_stopped.connect(self.handle_recording_stopped)

        return recorder

    def _init_ui(self):
        # Camera Combo Box
        self.combo_cameras = MarqueeComboBox()
        self.camera_label = QLabel("Camera:")
        self.combo_resolutions = MarqueeComboBox()
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

    @staticmethod
    def _is_ir_camera_name(camera_name) -> bool:
        return bool(camera_name) and ("ir" in str(camera_name).lower())

    def _preferred_video_format_change(self, event):
        strict_flag = "strictly" if self.preferences.strict_video_format else ""
        logger.critical(
            f"Preferred video format changed to: "
            f"{self.preferences.preferred_video_format} {strict_flag}"
        )
        self.populate_resolutions()

    # ------------------------------------------------------------------ #
    # Camera on / off                                                      #
    # ------------------------------------------------------------------ #
    def _set_camera_active(self, active):
        """Sync the toggle button and the model with the camera's state."""
        self.camera_toggle_button.setText("videocam" if active else "videocam_off")
        self.camera_toggle_button.setToolTip("Camera On" if active else "Camera Off")
        self.camera_toggle_button.setChecked(active)

        self.camera_model.camera_active = active

    def turn_on_camera(self):
        logger.info("Turning camera on")

        if self.camera_model.provider_selected:
            if self._active_feed is None:
                self._start_provider_feed()

            self._set_camera_active(True)

            return

        if not self.camera_device.is_active():
            self.camera_device.start()
            self._set_camera_active(True)

    def turn_off_camera(self):
        logger.info("Turning camera off")

        if self.camera_model.provider_selected:
            self._stop_provider_feed()
            self._set_camera_active(False)

            return

        if self.camera_device.is_active():
            self.camera_device.stop()
            self._set_camera_active(False)

    def toggle_camera(self):
        choice = OK

        if self.recorder.is_recording:
            choice = warning(
                None,
                title="Recording Session Active Warning",
                message="Are you sure you want to shut off the camera while recording?",
            )

        if choice in (OK, YES):
            self.turn_off_camera() if self._feed_active() else self.turn_on_camera()
        else:
            # Revert the button's checked state since Qt auto-toggles it on click
            self.camera_toggle_button.setChecked(self._feed_active())

        # keep the camera toggled button in sync with the alpha map.
        self.model.set_visible(video_key, self._feed_active())

    def check_initial_camera_state(self):
        """Sync the camera toggle button with the actual camera state."""
        self._set_camera_active(self.camera_device.is_active())

    @Slot(bool)
    def on_camera_active(self, active):
        if active:
            self.turn_on_camera()
        else:
            self.turn_off_camera()

    def _feed_active(self) -> bool:
        """True while any video source is live (QCamera or provider feed)."""
        return self._active_feed is not None or self.camera_device.is_active()

    # ------------------------------------------------------------------ #
    # Camera perspective                                                   #
    # ------------------------------------------------------------------ #
    def toggle_align_camera_mode(self):
        if self.model.mode == "camera-edit" or (
            self.model.mode != "camera-edit" and self.can_enter_edit_mode()
        ):
            self.model.flip_mode_activation("camera-edit")
        else:
            self.model.flip_mode_activation("camera-place")

    def can_enter_edit_mode(self) -> bool:
        return self.model.camera_perspective.perspective_transformation_possible()

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

    # ------------------------------------------------------------------ #
    # Provider sources (CAMERA_SOURCES extension point)                    #
    # ------------------------------------------------------------------ #
    def _select_provider_source(self, was_running):
        """Route the capture path to a provider source: no QCamera. The
        video layer starts hidden — the feed's streaming signal shows it
        when the provider's own preview toggle is on (see
        _on_feed_streaming); captures don't need it either way: they save
        the feed's raw frame."""
        self.camera_device.unbind()
        self.video_item.setVisible(False)
        self._disable_camera_buttons(False)

        # The recorder taps the QtMultimedia session, which provider feeds
        # bypass; screen captures still work (they grab the scene).
        self.record_toggle_button.setDisabled(True)
        self.combo_resolutions.blockSignals(True)
        self.combo_resolutions.clear()  # providers stream full resolution
        self.combo_resolutions.blockSignals(False)

        if was_running:
            self.turn_on_camera()

    def _start_provider_feed(self):
        label = self.camera_model.selected_camera
        provider, key = self._provider_sources[label]

        try:
            feed = provider.open(key)
        except Exception as e:
            logger.error(f"Camera-source feed for '{label}' failed to open: {e}")
            return

        feed.error.connect(self._on_feed_error)

        # Optional preview: a feed may emit display frames plus a streaming
        # state (e.g. driven by a checkbox in the contributing plugin's own
        # pane) — the video layer shows only while the feed reports an
        # active stream.
        frame_signal = getattr(feed, "frame", None)

        if frame_signal is not None:
            frame_signal.connect(self.camera_device.forward_preview_image)

        streaming_signal = getattr(feed, "streaming", None)

        if streaming_signal is not None:
            streaming_signal.connect(self._on_feed_streaming)

        controls = None
        create_controls = getattr(feed, "create_controls", None)

        if create_controls is not None:
            controls = create_controls(self)

        if controls is not None:
            self.layout().addWidget(controls)

        self._feed_controls = controls
        self._active_feed = feed
        self.camera_model.provider_feed_active = True
        feed.start()
        logger.info(f"Provider camera feed started: {label}")

    def _stop_provider_feed(self):
        if self._active_feed is None:
            return

        try:
            self._active_feed.stop()
        except Exception:
            logger.error("Provider feed failed to stop cleanly", exc_info=True)

        if self._feed_controls is not None:
            self.layout().removeWidget(self._feed_controls)
            self._feed_controls.deleteLater()
            self._feed_controls = None

        self._active_feed = None
        self.camera_model.provider_feed_active = False

        # Recording stays unavailable while a provider source is selected
        # (provider feeds bypass the QtMultimedia session the recorder taps).
        self.record_toggle_button.setDisabled(self.camera_model.provider_selected)
        # No feed, no stream: hide the video layer (a QCamera selection
        # re-shows it in on_camera_changed).
        self.video_item.setVisible(False)
        logger.info("Provider camera feed stopped")

    def _on_feed_streaming(self, active):
        """Provider feeds own their preview state (e.g. the fluorescence
        pane's stream checkbox): show the video layer only while the feed
        reports an active stream."""
        self.video_item.setVisible(active)

    def _on_feed_error(self, message):
        logger.error(f"Provider camera feed error: {message}")
        self.turn_off_camera()

    # ------------------------------------------------------------------ #
    # Source and format selection                                          #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _get_camera_description(selected_device):
        """Return a human-readable identifier for a camera device.

        LinuxCameraDeviceContainer returns the /dev/videoN path (unique on Linux),
        while QCameraDevice returns the Qt-provided description string.
        """
        if isinstance(selected_device, LinuxCameraDeviceContainer):
            return selected_device.device_path

        return selected_device.description()

    def _get_camera_resolution_max_framerate(self, w=0, h=0, fmt=None):
        """Return the max framerate for a given resolution, or 0.0 if unknown.

        On most platforms Qt's QCameraFormat.maxFrameRate() returns the correct
        value.  On Linux, however, it often reports 0 because the GStreamer
        backend does not populate this field.  In that case we fall back to
        V4L2 data stored in the LinuxCameraDeviceContainer for this camera.

        Args:
            w: Resolution width (used when ``fmt`` is not provided).
            h: Resolution height (used when ``fmt`` is not provided).
            fmt: A QCameraFormat to extract resolution and fps from.
        """

        # Try the Qt-reported fps first (reliable on Windows/macOS)
        if isinstance(fmt, QCameraFormat):
            _qt_fps = fmt.maxFrameRate()

            if _qt_fps:
                return _qt_fps

            w = fmt.resolution().width()
            h = fmt.resolution().height()

        # Fall back to V4L2 fps data on Linux
        _container = self._linux_device_containers.get(
            self.camera_model.selected_camera
        )

        if _container:
            return _container.get_fps(w, h)

        return 0.0

    def initialize_camera_list(self):
        current_label = self.combo_cameras.currentText()

        _available_cameras = get_video_inputs()
        self.combo_cameras.clear()
        self.combo_cameras.blockSignals(True)
        self._linux_device_containers.clear()

        camera_labels = []

        for camera in _available_cameras:
            description = self._get_camera_description(camera)
            camera_labels.append(description)

            if isinstance(camera, LinuxCameraDeviceContainer):
                # Store the container in a side dict for V4L2 fps lookups.
                # Only the underlying QCameraDevice goes into combo userData
                # (shiboken crashes on non-Qt types in QVariant).
                self._linux_device_containers[description] = camera
                self.combo_cameras.addItem(description, userData=camera.camera_device)
            else:
                self.combo_cameras.addItem(description, userData=camera)

        # provider-contributed sources (ASI cameras etc.)
        self._provider_sources.clear()
        provider_labels = []

        if callable(self.source_providers):
            providers = self.source_providers()
        else:
            providers = self.source_providers or []

        for provider in providers:
            try:
                for label, key in provider.list_sources():
                    self._provider_sources[label] = (provider, key)
                    provider_labels.append(label)
                    self.combo_cameras.addItem(label, userData=None)
            except Exception:
                logger.error(
                    f"Camera-source provider {provider!r} failed to "
                    "enumerate; skipping",
                    exc_info=True,
                )

        # account for no camera
        self.combo_cameras.addItem("<No Camera>", userData=None)

        self.combo_cameras.blockSignals(False)

        self.combo_cameras.setCurrentIndex(-1)
        self.combo_cameras.setCurrentIndex(
            self.controller.choose_camera_index(
                camera_labels, provider_labels, current_label
            )
        )

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
        label = self.combo_cameras.itemText(index)

        was_running = self._feed_active()
        self._stop_provider_feed()

        if self.camera_device.is_active():
            self.turn_off_camera()
            was_running = True

        if label in self._provider_sources:
            self.controller.select_source(label, remembered_as=label, provider=True)
            self._select_provider_source(was_running)

            return

        if camera:
            container = self._linux_device_containers.get(label)

            self.camera_device.bind(camera)
            self.controller.select_source(
                label,
                remembered_as=self._get_camera_description(camera),
                v4l2_device_path=container.device_path if container else None,
            )
            self.video_item.setVisible(True)
            self._disable_camera_buttons(False)

        else:
            # "<No Camera>": the previous QCamera (if any) stays bound, off.
            self.controller.select_source("")
            self._disable_camera_buttons(True)

        self.populate_resolutions()

        if was_running and camera:
            self.turn_on_camera()

    def populate_resolutions(self, allow_strict_mode=True):
        """Populate the resolution combo box from the current camera's formats.

        One entry per resolution, best first (see
        CameraController.rank_formats); under the strict-format preference,
        if no format matches, retry once without it. Then restore the saved
        resolution, falling back to the middle entry.
        """
        self.combo_resolutions.blockSignals(True)
        self.combo_resolutions.clear()

        if not self.camera_device.has_camera():
            # No QCamera bound (provider source or "<No Camera>"): nothing
            # to enumerate.
            self.combo_resolutions.blockSignals(False)
            return

        formats = self.camera_device.video_formats()
        format_summaries = [
            (
                fmt.resolution().width(),
                fmt.resolution().height(),
                str(fmt.pixelFormat()),
                fmt.maxFrameRate(),
            )
            for fmt in formats
        ]

        for index in self.controller.rank_formats(format_summaries, allow_strict_mode):
            fmt = formats[index]
            w, h = fmt.resolution().width(), fmt.resolution().height()
            fps = self._get_camera_resolution_max_framerate(fmt=fmt)
            pix_name = str(fmt.pixelFormat()).split(".")[-1].replace("Format_", "")
            label = f"{w}x{h} [{pix_name}] @ {fps:.0f} fps"
            self.combo_resolutions.addItem(label, userData=fmt)

        self.combo_resolutions.blockSignals(False)

        labels = [
            self.combo_resolutions.itemText(i)
            for i in range(self.combo_resolutions.count())
        ]

        if labels:
            self.combo_resolutions.setCurrentIndex(
                self.controller.choose_resolution_index(labels)
            )
        elif self.preferences.strict_video_format:
            # No formats survived strict filtering — retry without it
            warning_message = (
                f"Preferred format "
                f"{self.preferences.preferred_video_format} not supported."
            )
            logger.warning(warning_message)

            if not self._is_ir_camera_name(self.preferences.selected_camera):
                warning(None, warning_message)

            self.populate_resolutions(allow_strict_mode=False)

            return

        # Ensure the model always has a resolution set (e.g. when the combo
        # index didn't change and on_resolution_changed was never triggered).
        if not self.model.camera_perspective.camera_resolution:
            self.on_resolution_changed(self.combo_resolutions.currentIndex())

    def on_resolution_changed(self, index):
        if self.combo_resolutions.count() == 0 or index < 0:
            return

        camera_format = self.combo_resolutions.itemData(index)
        was_running = self.camera_device.is_active()

        if was_running:
            self.camera_device.stop()
            QApplication.processEvents()

        self.camera_device.set_format(camera_format)

        resolution = (
            camera_format.resolution().width(),
            camera_format.resolution().height(),
        )
        self.controller.select_resolution(
            self.combo_resolutions.itemText(index),
            *resolution,
            self._get_camera_resolution_max_framerate(fmt=camera_format),
        )
        self.model.camera_perspective.camera_resolution = resolution

        if was_running:
            self.camera_device.start()

    # ------------------------------------------------------------------ #
    # Image capture                                                        #
    # ------------------------------------------------------------------ #
    def _capture_image_routine(self, capture_data=None):
        save_path, show_status_message, request_id = self.controller.capture_target(
            capture_data
        )

        # Always a display grab, whatever the active feed. Raw (16-bit)
        # sensor captures are the owning plugin's concern — the
        # fluorescence capture chain writes its own per-burst folders —
        # so this pipeline no longer special-cases raw-capable feeds.
        self._capture_display_image(save_path, show_status_message, request_id)

    def _capture_display_image(self, save_path, show_status_message, request_id=""):
        # Capture Pixels (Must happen on UI thread)
        image = self.get_screen_shot()

        if not image or image.isNull():
            return

        save_path.parent.mkdir(parents=True, exist_ok=True)

        def _post_image_capture(saved_path):
            self.controller.image_saved(saved_path, request_id)

            if show_status_message:
                _show_media_capture_status_message(
                    MediaType.IMAGE, saved_path, self.status_bar_manager
                )

        # get_screen_shot may return the recorder's live current_image, which
        # the recorder keeps painting into — snapshot it before handing off.
        self._start_image_saver(image.copy(), str(save_path), _post_image_capture)

    def _start_image_saver(self, image, save_path, on_saved, on_failed=None):
        """Run an ImageSaver on the global thread pool — PNG-encoding a
        full-resolution frame inline visibly freezes the GUI. The worker is
        kept referenced until one of its completion signals (delivered queued
        on the GUI thread) has fired; ``on_saved``/``on_failed`` then run on
        the GUI thread."""
        worker = ImageSaver(image, save_path)
        self._pending_image_savers.add(worker)

        def _finish(saved_path, callback):
            self._pending_image_savers.discard(worker)

            if callback is not None:
                callback(saved_path)

        worker.signals.save_complete.connect(
            lambda saved_path: _finish(saved_path, on_saved)
        )
        worker.signals.save_failed.connect(
            lambda saved_path: _finish(saved_path, on_failed)
        )
        QThreadPool.globalInstance().start(worker)

    def _capture_image_and_close(self, capture_data):
        self._capture_image_routine(capture_data)
        self.toggle_camera()

    @Slot()
    def capture_button_handler(self, capture_data=None):

        # Feed-aware: provider sources (ASI) have no QCamera; the screen
        # grab captures whatever the video layer shows either way.
        if self._feed_active():
            self._capture_image_routine(capture_data)

        else:
            self.toggle_camera()
            QTimer.singleShot(1000, lambda: self._capture_image_and_close(capture_data))

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

        resolution_format = self.combo_resolutions.currentData()

        if resolution_format is not None:
            target_resolution_size = resolution_format.resolution()
        else:
            # Provider sources have no QCameraFormat list; they stream at
            # native resolution, so the frame itself is the target size.
            target_resolution_size = source_image.size()

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

    # ------------------------------------------------------------------ #
    # Exposure / focus                                                     #
    # ------------------------------------------------------------------ #
    @Slot(object)
    def apply_camera_controls(self, request):
        """Apply a CameraControlsRequest dict on the GUI thread; the
        controller answers DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED."""
        self.controller.apply_camera_controls(request)

    # ------------------------------------------------------------------ #
    # Video recording (background thread)                                  #
    # ------------------------------------------------------------------ #
    def on_recording_active(self, recording_data):
        if isinstance(recording_data, dict):
            action = recording_data.get("action", "").lower()

            if action == "start":
                self.video_record_start(
                    recording_data.get("directory"),
                    recording_data.get("step_description"),
                    recording_data.get("step_id"),
                    recording_data.get("show_status_message", True),
                )
                # Reflect what actually happened — the start is refused for
                # provider feeds (ASI) and unsupported frame rates.
                self.record_toggle_button.setChecked(self.recorder.is_recording)
            elif action == "stop":
                self.video_record_stop()
                self.record_toggle_button.setChecked(False)
        else:
            logger.error(f"Invalid recording data: {recording_data}")

    @Slot()
    def toggle_recording(self):
        if self.recorder.is_recording:
            self.video_record_stop()
        else:
            self.video_record_start()

    @Slot()
    def video_record_start(
        self,
        directory=None,
        step_description=None,
        step_id=None,
        show_status_message=True,
    ):
        logger.info("Starting video recorder...")

        # A rebuild while recording would orphan the active recorder.
        if self.recorder.is_recording:
            return

        # Provider feeds (ASI) bypass the QtMultimedia session the recorder
        # taps: recording is unsupported for them. The button is disabled
        # while a provider source is selected, so this guard covers the
        # protocol/message-driven path.
        if self.camera_model.provider_selected or not self.camera_device.has_camera():
            logger.warning(
                "Video recording is not supported for the selected camera source"
            )
            self.record_toggle_button.setChecked(False)
            return

        # Check fps threshold before starting
        _current_fmt = self.combo_resolutions.currentData()
        fps = self._get_camera_resolution_max_framerate(fmt=_current_fmt)

        if not self.controller.recording_frame_rate_supported(fps):
            disclaimer(
                parent=None,
                title="Recording Not Supported",
                message=(
                    f"Cannot record at <b>{fps:.0f} fps</b>. "
                    f"Minimum supported frame rate for recording is "
                    f"<b>{MIN_RECORDING_FPS} fps</b>.\n\n"
                    f"Please select a resolution with a higher frame rate."
                ),
                ack_button_text="OK",
            )
            self.record_toggle_button.setChecked(False)
            return

        camera_was_on = self.camera_device.is_active()

        if not camera_was_on:
            self.toggle_camera()

        recording_path = self.controller.prepare_recording(
            directory, step_description, step_id, show_status_message, camera_was_on
        )

        _resolution = (
            _current_fmt.resolution().width(),
            _current_fmt.resolution().height(),
        )

        # Rebuild from current preferences so backend/container/bitrate
        # changes apply without a restart, with the bitrate class matched
        # to the actual camera resolution and frame rate.
        self.recorder = self._build_recorder(_resolution, fps)
        self.recorder.start(recording_path, _resolution, fps)
        self.controller.recording_started()

    def video_record_stop(self):
        logger.info("Stopping video recorder...")
        self.recorder.stop()

    @Slot(str)
    def handle_recording_error(self, error_msg):
        logger.error(f"Recording Error: {error_msg}")
        self.controller.recording_ended()
        error(
            self,
            "<b>Error</b>: Cannot continue to record video<br><br>"
            "Exception raised while recording video.",
            detail=error_msg,
        )
        self.video_record_stop()

    @Slot(str)
    def handle_recording_stopped(self, recording_output_path):
        turn_camera_off = self.controller.recording_ended()

        if turn_camera_off and self.camera_device.is_active():
            self.toggle_camera()

        # Show Result
        if recording_output_path and self.camera_model.recording.show_status_message:
            _show_media_capture_status_message(
                MediaType.VIDEO, recording_output_path, self.status_bar_manager
            )

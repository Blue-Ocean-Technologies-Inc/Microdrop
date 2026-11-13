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
from pyface.qt.QtMultimedia import QCameraFormat
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
from microdrop_style.icons.icons import ICON_VIEW_3D

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import MarqueeComboBox
from microdrop_utils.v4l2_fps_getter import (
    LinuxCameraDeviceContainer,
    get_video_inputs,
)

# Local imports.
from ...consts import (
    CAMERA_FEED_START_TIMEOUT_MS,
    CAMERA_MIN_RESOLUTION,
    COMMON_RESOLUTION_NAMES,
    HIGH_RESOLUTION_WARNING_THRESHOLD,
    MIN_RECORDING_FPS,
    NO_CAMERA_LABEL,
    SHOW_ALL_RESOLUTIONS_LABEL,
    SHOW_COMMON_RESOLUTIONS_LABEL,
)
from ...controllers.camera_controller import CameraController
from ...default_settings import video_key
from ...models.camera import CameraModel
from ...models.media import MediaType
from ...models.recording_overlay import RecordingOverlayTimeline
from ...utils.capture import ImageSaver, get_transformed_frame
from ...utils.frame_luma import frame_centre_luma
from ...utils.recording.factory import build_recorder
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

    #: A CameraSelectSourceRequest dict, emitted by the dock pane's topic
    #: handler (a Dramatiq worker thread) and applied on the GUI thread.
    camera_select_source_signal = Signal(object)

    #: A CameraSettingsRequest dict, emitted by the dock pane's topic
    #: handler (a Dramatiq worker thread) and applied on the GUI thread.
    camera_settings_signal = Signal(object)

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
        # The select_source request (dict) whose reply waits on a
        # just-started provider feed's outcome; see apply_select_source.
        self._pending_select_source = None
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
            video_item=self.video_item, preview_receiver=self._forward_preview_frame
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
        self.camera_select_source_signal.connect(self.apply_select_source)
        self.camera_settings_signal.connect(self.apply_camera_settings)

        # UI Initialization
        self._init_ui()

        # Check initial camera state
        self.initialize_camera_list()
        self.check_initial_camera_state()

    def _build_recorder(self, resolution=None, fps=None):
        """The preferences' recorder (see build_recorder), wired to this
        panel's recording handlers."""
        recorder = build_recorder(
            self.preferences,
            self.camera_device.session,
            self.camera_device.sink,
            self.video_item,
            resolution,
            fps,
        )

        recorder.error_occurred.connect(self.handle_recording_error)
        recorder.recording_stopped.connect(self.handle_recording_stopped)

        return recorder

    def _init_ui(self):
        # Camera Combo Box
        self.combo_cameras = MarqueeComboBox()
        self.camera_label = QLabel("Camera:")
        self.combo_resolutions = MarqueeComboBox()
        # Whether the combo lists every camera format or only the common
        # sizes (see populate_resolutions).
        self._show_all_resolutions = False
        self.resolution_label = QLabel("Resolution: ")
        self.camera_select_layout = QHBoxLayout()
        self.camera_select_layout.addWidget(self.camera_label)
        self.camera_select_layout.addWidget(self.combo_cameras)

        self.resolution_select_layout = QHBoxLayout()
        self.resolution_select_layout.addWidget(self.resolution_label)
        self.resolution_select_layout.addWidget(self.combo_resolutions)

        # Buttons
        self.button_align = QPushButton(ICON_VIEW_3D)
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

        # "<No Camera>" keeps the previous QCamera bound; never start it.
        if not self.camera_model.selected_camera:
            logger.warning("No camera source selected; the camera stays off")
            return

        if self.camera_model.provider_selected:
            if self._active_feed is None:
                self._start_provider_feed()

            # A feed that failed to open (logged there) leaves the camera off.
            self._set_camera_active(self._active_feed is not None)

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
            self.camera_model.feed_error = str(e)

            return

        self.camera_model.feed_error = ""
        feed.error.connect(self._on_feed_error)

        # Optional preview: a feed may emit display frames plus a streaming
        # state (e.g. driven by a checkbox in the contributing plugin's own
        # pane) — the video layer shows only while the feed reports an
        # active stream.
        frame_signal = getattr(feed, "frame", None)

        if frame_signal is not None:
            frame_signal.connect(self._forward_preview_image)

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

    # Frames are emitted on capture / feed worker threads. Receiving them on
    # this QObject queues them onto the GUI thread; a plain-Python receiver
    # would run on the worker thread and touch the video item from there,
    # which stalls or kills the preview within seconds.
    def _forward_preview_frame(self, frame):
        self.camera_device.forward_preview_frame(frame)

        # A running autofocus sweep measures every frame, not the preview's.
        if self.camera_model.focus.autofocusing:
            self.controller.autofocus_frame(frame_centre_luma(frame))

    def _forward_preview_image(self, image):
        self.camera_device.forward_preview_image(image)

    def _on_feed_streaming(self, active):
        """Provider feeds own their preview state (e.g. the fluorescence
        pane's stream checkbox): show the video layer only while the feed
        reports an active stream."""
        self.video_item.setVisible(active)

    def _on_feed_error(self, message):
        logger.error(f"Provider camera feed error: {message}")
        self.camera_model.feed_error = message
        self.turn_off_camera()
        self._finish_pending_select_source()

    # ------------------------------------------------------------------ #
    # Source and format selection                                          #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _get_camera_description(selected_device):
        """Return a human-readable identifier for a camera device.

        LinuxCameraDeviceContainer returns the /dev/videoN path (unique on Linux),
        while QCameraDevice — and a container without a node, e.g. a libcamera
        device — returns the Qt-provided description string.
        """
        if isinstance(selected_device, LinuxCameraDeviceContainer):
            if selected_device.device_path:
                return selected_device.device_path

            selected_device = selected_device.camera_device

        return selected_device.description()

    def _get_camera_resolution_max_framerate(self, w=0, h=0, fmt=None):
        """Return the max framerate for a given resolution, or 0.0 if unknown.

        On most platforms Qt's QCameraFormat.maxFrameRate() returns the correct
        value.  On Linux, however, it often reports 0 because the GStreamer
        backend does not populate this field.  In that case we fall back to
        V4L2 data stored in the LinuxCameraDeviceContainer for this camera
        (for a libcamera camera, its sensor modes).

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
        self.combo_cameras.addItem(NO_CAMERA_LABEL, userData=None)

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
                v4l2_focus_device_path=(
                    container.focus_device_path if container else None
                ),
                v4l2_focus_lens_map=container.focus_lens_map if container else (),
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
        CameraController.rank_formats); under the controller's strict format
        mode, if no format matches, retry once without it. By default only
        the common sizes (COMMON_RESOLUTION_NAMES) are listed, named, plus
        the saved size when it is not one of them, with a last entry that
        switches to the full list; the full list ends with the entry that
        switches back. Then restore the saved resolution, falling back to
        the middle entry.
        """
        self.combo_resolutions.blockSignals(True)
        self.combo_resolutions.clear()

        if not self.camera_device.has_camera():
            # No QCamera bound (provider source or "<No Camera>"): nothing
            # to enumerate.
            self.combo_resolutions.blockSignals(False)
            return

        libcamera = self.camera_device.is_libcamera()
        ranked = self._ranked_formats(allow_strict_mode)
        saved_resolution = self.preferences.resolution

        # The condensed list: the common sizes, plus the saved size when it is
        # not one of them, so a saved pick still restores. The full list only
        # when asked for or when the camera has none of the common sizes.
        common = [
            fmt
            for fmt in ranked
            if self._resolution_name(fmt)
            or self._resolution_label(fmt) == saved_resolution
        ]
        show_all = self._show_all_resolutions or not common
        listed = ranked if show_all else common
        labels = [self._resolution_label(fmt) for fmt in listed]

        for fmt, label in zip(listed, labels):
            self.combo_resolutions.addItem(label, userData=fmt)

        if ranked:
            self.combo_resolutions.addItem(
                SHOW_COMMON_RESOLUTIONS_LABEL
                if show_all
                else SHOW_ALL_RESOLUTIONS_LABEL
            )

        self._show_all_resolutions = show_all
        self.combo_resolutions.blockSignals(False)

        if labels:
            # Restored, not picked: apply the format without the signal, so
            # the high-resolution notice cannot interrupt start-up.
            index = self.controller.choose_resolution_index(labels)
            self.combo_resolutions.blockSignals(True)
            self.combo_resolutions.setCurrentIndex(index)
            self.combo_resolutions.blockSignals(False)
            self.on_resolution_changed(index, interactive=False)
        elif self.controller.strict_format_mode(allow_strict_mode, libcamera):
            # No formats survived strict filtering — retry without it
            warning_message = (
                f"Preferred format "
                f"{self.preferences.preferred_video_format} not supported."
            )
            logger.warning(warning_message)

            if not self._is_ir_camera_name(self.preferences.selected_camera):
                warning(None, warning_message)

            self.populate_resolutions(allow_strict_mode=False)

    def _ranked_formats(self, allow_strict_mode=True):
        """The bound camera's formats of at least CAMERA_MIN_RESOLUTION, one
        per resolution, best first (see CameraController.rank_formats)."""
        min_width, min_height = CAMERA_MIN_RESOLUTION
        formats = [
            fmt
            for fmt in self.camera_device.video_formats()
            if fmt.resolution().width() >= min_width
            and fmt.resolution().height() >= min_height
        ]
        format_summaries = [
            (
                fmt.resolution().width(),
                fmt.resolution().height(),
                str(fmt.pixelFormat()),
                fmt.maxFrameRate(),
            )
            for fmt in formats
        ]
        ranked_indices = self.controller.rank_formats(
            format_summaries, allow_strict_mode, self.camera_device.is_libcamera()
        )

        return [formats[index] for index in ranked_indices]

    @staticmethod
    def _resolution_name(fmt):
        """The common name of a format's size ("FHD"), or None."""
        return COMMON_RESOLUTION_NAMES.get(
            (fmt.resolution().width(), fmt.resolution().height())
        )

    def _resolution_label(self, fmt):
        """The combo label of a format: its common name when it has one,
        then the size, pixel format and frame rate."""
        w, h = fmt.resolution().width(), fmt.resolution().height()
        fps = self._get_camera_resolution_max_framerate(fmt=fmt)
        pix_name = str(fmt.pixelFormat()).split(".")[-1].replace("Format_", "")
        name = self._resolution_name(fmt)
        size = f"{name} ({w}x{h})" if name else f"{w}x{h}"

        return f"{size} [{pix_name}] @ {fps:.0f} fps"

    def _toggle_resolution_list(self):
        """Switch between the common and the full resolution list, keeping
        the selected format."""
        selected = self.camera_model.resolution
        self._show_all_resolutions = not self._show_all_resolutions
        self.populate_resolutions()

        for index in range(self.combo_resolutions.count()):
            fmt = self.combo_resolutions.itemData(index)

            if fmt is not None and (
                (fmt.resolution().width(), fmt.resolution().height()) == selected
            ):
                self.combo_resolutions.blockSignals(True)
                self.combo_resolutions.setCurrentIndex(index)
                self.combo_resolutions.blockSignals(False)

                return

    def on_resolution_changed(self, index, interactive=True):
        """Apply the combo's format at ``index``. ``interactive`` is False for
        the restore at start-up, which never shows the high-resolution
        notice."""
        if self.combo_resolutions.count() == 0 or index < 0:
            return

        camera_format = self.combo_resolutions.itemData(index)

        # The list-switching entry carries no format.
        if camera_format is None:
            self._toggle_resolution_list()

            return

        self.camera_device.apply_format(camera_format)

        resolution = (
            camera_format.resolution().width(),
            camera_format.resolution().height(),
        )

        if interactive:
            self._warn_high_resolution(resolution)
        self.controller.select_resolution(
            self.combo_resolutions.itemText(index),
            *resolution,
            self._get_camera_resolution_max_framerate(fmt=camera_format),
            user_edit=interactive,
        )
        self.model.camera_perspective.camera_resolution = resolution

    def _warn_high_resolution(self, resolution):
        """Tell the user a size above Full HD can slow the app down, unless
        they asked not to be told again."""
        max_width, max_height = HIGH_RESOLUTION_WARNING_THRESHOLD
        width, height = resolution

        if width <= max_width and height <= max_height:
            return

        if self.preferences.suppress_high_resolution_warning:
            return

        _, dont_show_again = warning(
            None,
            title="High resolution selected",
            message=(
                f"{width}x{height} is above Full HD ({max_width}x{max_height}). "
                f"Streaming, recording and image analysis at this size put "
                f"more load on the camera pipeline and can slow the app down, "
                f"especially on the portable instrument."
            ),
            cancel=False,
            checkbox_text="Don't show this again (can be undone from "
            "Preferences \u203a Video Settings)",
        )

        if not dont_show_again:
            return

        self.preferences.suppress_high_resolution_warning = True

        try:
            self.preferences.preferences.flush()
        except OSError as error:
            logger.error(f"Could not save camera preferences: {error}")

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
    # Capture setup by request (CameraSettingsRequest)                     #
    # ------------------------------------------------------------------ #
    @Slot(object)
    def apply_camera_settings(self, request):
        """Apply a CameraSettingsRequest dict — a protocol step's capture
        setup — to the selected QCamera: its resolution here, the camera
        properties through the controller, which answers
        DEVICE_VIEWER_CAMERA_SETTINGS_APPLIED. What the camera cannot take
        is skipped and the user warned, once per camera and warning."""
        if not self.controller.qcamera_selected():
            self.controller.settings_applied(request, error="no QCamera is selected")

            return

        self.controller.begin_applying_settings()
        warnings = []

        try:
            if request["resolution"] is not None:
                warnings.extend(
                    self._apply_requested_resolution(tuple(request["resolution"]))
                )

            warnings.extend(self.controller.apply_settings(request))
        except Exception as e:
            logger.error(f"Capture setup not applied: {e}", exc_info=True)
            self.controller.settings_applied(request, warnings, error=str(e))

            return

        self.controller.settings_applied(request, warnings)
        self._warn_unsupported_settings(
            request["context"], self.controller.unseen_settings_warnings(warnings)
        )

    def _apply_requested_resolution(self, resolution):
        """Switch to the best format of ``resolution`` — selected as if
        restored, so it shows in the combo even when it is not a common
        size; returns the warnings (the size is not supported)."""
        if self.camera_model.resolution == resolution:
            return []

        ranked = self._ranked_formats() or self._ranked_formats(allow_strict_mode=False)
        match = next(
            (
                fmt
                for fmt in ranked
                if (fmt.resolution().width(), fmt.resolution().height()) == resolution
            ),
            None,
        )

        if match is None:
            width, height = resolution
            current_width, current_height = self.camera_model.resolution

            return [
                f"{width}x{height} is not supported by "
                f"{self.camera_model.selected_camera}; capturing at "
                f"{current_width}x{current_height} instead"
            ]

        # The condensed list always holds the saved size, and the restore
        # applies the format without the high-resolution notice.
        self.preferences.resolution = self._resolution_label(match)
        self.populate_resolutions()

        return []

    def _warn_unsupported_settings(self, context, warnings):
        """Tell the user what of a step's capture setup the camera could not
        take, so the step can be changed to settings it supports. Deferred
        out of the request's slot: the dialog is modal."""
        if not warnings:
            return

        where = f" for {context}" if context else ""
        message = (
            f"The camera cannot apply all of the capture settings{where}:<br><br>"
            + "<br>".join(f"\u2022 {text}" for text in warnings)
            + "<br><br>Select the step and pick settings this camera supports "
            "in the camera panel to update it."
        )

        QTimer.singleShot(
            0,
            lambda: warning(
                None,
                title="Capture settings not supported",
                message=message,
                cancel=False,
            ),
        )

    # ------------------------------------------------------------------ #
    # Source selection by request (CameraSelectSourceRequest)              #
    # ------------------------------------------------------------------ #
    @Slot(object)
    def apply_select_source(self, request):
        """Select the dropdown entry a CameraSelectSourceRequest dict names,
        through the same path as a click, then switch the camera on/off if
        asked; the controller answers DEVICE_VIEWER_CAMERA_SOURCE_SELECTED.

        A provider feed opens synchronously (an open failure is answered at
        once, with its message) but may start asynchronously, so when the
        request starts a new feed the reply waits for its outcome: the
        feed's first ``error`` answers ok=False with that message, its
        optional ``started`` signal — or CAMERA_FEED_START_TIMEOUT_MS
        passing without an error — answers ok. A QCamera's start is not
        waited on: ok=True means the selection and start request went
        through, and a camera failing later shows as active=False on
        DEVICE_VIEWER_CAMERA_STATE.
        """
        labels = [
            self.combo_cameras.itemText(index)
            for index in range(self.combo_cameras.count())
        ]
        index = self.controller.find_requested_source(request, labels)

        if index is None:
            return

        error = ""
        feed_before = self._active_feed

        # Provider feeds are other plugins' code: any exception they raise
        # while switching over is answered as a failure, not left to Qt.
        try:
            self.combo_cameras.setCurrentIndex(index)

            if request["active"] is not None:
                self.on_camera_active(request["active"])
        except Exception as e:
            logger.error(f"Camera source {request['label']!r}: {e}", exc_info=True)
            error = f"camera source {request['label']!r} failed: {e}"

        feed = self._active_feed

        if not error and request["active"] and feed not in (None, feed_before):
            self._await_feed_start(request, feed)

            return

        self.controller.source_selected(request, error)

    def _await_feed_start(self, request, feed):
        """Hold ``request``'s reply until ``feed`` starts, fails, or
        CAMERA_FEED_START_TIMEOUT_MS passes (see apply_select_source)."""

        # An earlier request still waiting is answered as things stand now.
        self._finish_pending_select_source()
        self._pending_select_source = request

        started = getattr(feed, "started", None)

        if started is not None:
            started.connect(self._finish_pending_select_source)

        QTimer.singleShot(
            CAMERA_FEED_START_TIMEOUT_MS,
            lambda: self._finish_pending_select_source(request),
        )

    def _finish_pending_select_source(self, request=None):
        """Answer the waiting select_source request, if any (only when it is
        ``request``, for the timeout of that one request)."""
        pending = self._pending_select_source

        if pending is None or (request is not None and request is not pending):
            return

        self._pending_select_source = None
        self.controller.source_selected(pending)

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

        # An unknown rate is no reason to refuse: the recorders fall back to
        # a default or the camera's delivery rate.
        if not fps:
            logger.warning("Camera frame rate unknown; recording anyway")

        elif not self.controller.recording_frame_rate_supported(fps):
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
        def start_recorder(sync_button=False):
            self.recorder = self._build_recorder(_resolution, fps)
            self.recorder.overlay_timeline = self._recording_overlay_timeline()
            self.recorder.start(recording_path, _resolution, fps)
            self.camera_device.hold_restarts = True
            self.controller.recording_started()

            # on_recording_active synced the button before a deferred start.
            if sync_button:
                self.record_toggle_button.setChecked(self.recorder.is_recording)

        # A libcamera camera switched off moments ago gets a new session and
        # sink on the next event-loop pass: record into those, not the old.
        if self.camera_device.rebuild_pending:
            self.camera_device.after_rebuild(lambda: start_recorder(sync_button=True))

            return

        start_recorder()

    def _recording_overlay_timeline(self):
        """A fresh device outline + actuation timeline for the recording
        about to start, already started — on the GUI thread, before the
        recorder can mark its time origin; None while no device is loaded."""
        interaction_service = self.scene.interaction_service

        if (
            interaction_service is None
            or interaction_service.electrode_view_layer is None
        ):
            return None

        timeline = RecordingOverlayTimeline(
            electrodes=self.model.electrodes,
            path_scale=interaction_service.electrode_view_layer.path_scale,
        )
        timeline.start()

        return timeline

    def video_record_stop(self):
        logger.info("Stopping video recorder...")
        self.recorder.stop()

    @Slot(str)
    def handle_recording_error(self, error_msg):
        logger.error(f"Recording Error: {error_msg}")
        self.camera_device.hold_restarts = False
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
        self.camera_device.hold_restarts = False
        turn_camera_off = self.controller.recording_ended()

        if turn_camera_off and self.camera_device.is_active():
            self.toggle_camera()

        # Show Result
        if recording_output_path and self.camera_model.recording.show_status_message:
            _show_media_capture_status_message(
                MediaType.VIDEO, recording_output_path, self.status_bar_manager
            )

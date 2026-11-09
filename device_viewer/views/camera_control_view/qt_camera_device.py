# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Qt camera stack behind the camera panel, as an ICameraDevice.

QCamera and QMediaCaptureSession are Qt objects that must live on the GUI
thread next to the video item they feed, so they stay in the view layer —
owned by the camera widget — rather than in the Qt-free model or
controller. The controller drives them through ICameraDevice only.

Where Qt has no API for a camera's controls, this adapter fills in from the
platform: lens focus over DirectShow on Windows, and image controls
(brightness, contrast, ...) over DirectShow, v4l2, or a Raspberry Pi CSI
camera's libcamerasrc element.

A libcamera camera (a Raspberry Pi CSI camera) needs that no QVideoFrame of
its previous stream exists when the next QCamera starts: libcamerasrc's
buffers pin the libcamera Camera, whose completion slot still points at the
destroyed element. So a stop blanks the preview, discards camera, session and
sink on the next event-loop pass, and builds a fresh stack once Qt has
destroyed them. Its format may change only while streaming; one chosen while
it is off is applied shortly after the next start. Its image controls apply
only as it starts, so a change restarts it once the changes settle.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.qt.QtCore import QTimer
from pyface.qt.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QCameraFormat,
    QMediaCaptureSession,
    QVideoFrame,
    QVideoSink,
)
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem
from pyface.qt.QtWidgets import QApplication
from traits.api import (
    Bool,
    Callable,
    Float,
    HasTraits,
    Instance,
    List,
    observe,
    provides,
)

# Microdrop utils imports.
from microdrop_utils import libcamera_gst_element
from microdrop_utils.camera_image_controls import (
    ICameraImageControls,
    LibcameraImageControls,
    V4l2ImageControls,
)
from microdrop_utils.directshow_camera_controls import (
    DirectShowCameraControls,
    open_directshow_camera_controls,
)
from microdrop_utils.v4l2_fps_getter import (
    LIBCAMERA_ID_PREFIX,
    LinuxCameraDeviceContainer,
    is_libcamera_device,
)

# Local imports.
from ...consts import (
    CAMERA_PREVIEW_MAX_FPS,
    LIBCAMERA_CONTROL_RESTART_DEBOUNCE_MS,
    LIBCAMERA_FIRST_FRAME_TIMEOUT_MS,
    LIBCAMERA_REBUILD_GAP_MS,
    NATIVE_CAMERA_PROPERTIES_EXCLUDED,
    PENDING_FORMAT_DELAY_MS,
)
from ...interfaces.i_camera_device import ICameraDevice

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(ICameraDevice)
class QtCameraDevice(HasTraits):
    """QCamera + QMediaCaptureSession, with the preview frame-rate cap."""

    #: Display item the (rate-capped) preview frames are forwarded to.
    video_item = Instance(QGraphicsVideoItem)

    #: Receiver of every sink frame. Must be a bound method of a QObject:
    #: frames arrive on the capture thread, and only a QObject receiver gets
    #: them queued onto the GUI thread.
    preview_receiver = Callable

    #: The session's own sink: frames arrive here at full camera rate, which
    #: is what the FFmpeg recorder taps.
    sink = Instance(QVideoSink, ())

    #: The capture session the camera and the Qt recorder are attached to.
    session = Instance(QMediaCaptureSession, ())

    #: The bound camera; None until a camera is selected.
    camera = Instance(QCamera)

    #: The selected camera's device; it leads ``camera`` while a libcamera
    #: rebuild is pending (the rebuild builds the camera for it).
    device = Instance(QCameraDevice)

    #: The bound camera's DirectShow controls (Windows); None elsewhere or
    #: for a camera without any.
    directshow_controls = Instance(DirectShowCameraControls)

    #: The bound camera's image controls; None for a camera without any.
    image_controls = Instance(ICameraImageControls)

    #: True from a libcamera camera's stop until its camera, session and
    #: sink are replaced (see the module docstring).
    rebuild_pending = Bool(False)

    #: While True (a recording is running), the restart that applies
    #: libcamera image-control changes is deferred until the hold lifts.
    hold_restarts = Bool(False)

    #: monotonic() time of the last frame forwarded to the display item.
    _last_preview_frame_time = Float(0.0)

    #: Whether a frame has arrived since the camera's last start (see
    #: _check_first_frame).
    _frame_since_start = Bool(False)

    #: The stopped libcamera camera, kept alive until the rebuild discards
    #: it (an unbind or rebind may already have replaced ``camera``).
    _stopped_camera = Instance(QCamera)

    #: The format the rebuilt camera gets; None leaves Qt's default.
    _rebuild_format = Instance(QCameraFormat)

    #: A format chosen while a libcamera camera was not streaming, applied
    #: in flight once it is (see _start_camera).
    _pending_format = Instance(QCameraFormat)

    #: Whether the rebuilt camera starts: a start was requested meanwhile.
    _start_after_rebuild = Bool(False)

    #: Called once the pending rebuild is done (see after_rebuild).
    _after_rebuild_callbacks = List(Callable)

    #: Single-shot debounce of the restart that applies libcamera image
    #: control changes (see _schedule_control_restart).
    _control_restart_timer = Instance(QTimer)

    #: A control restart was deferred by hold_restarts.
    _restart_due = Bool(False)

    def traits_init(self):
        self._wire_session()

    def _wire_session(self):
        """Feed the session to the sink, and the sink's frames to the
        preview receiver."""
        self.session.setVideoSink(self.sink)

        if self.preview_receiver is not None:
            self.sink.videoFrameChanged.connect(self.preview_receiver)

    # ------------------------------------------------------------------ #
    # Binding                                                              #
    # ------------------------------------------------------------------ #
    def bind(self, selected_device):
        """Bind a camera built from a LinuxCameraDeviceContainer (which
        carries V4L2 metadata) or a QCameraDevice; unknown devices leave
        the session without a camera."""
        device = _qt_camera_device(selected_device)

        # A format chosen for the previous device does not carry over.
        if device != self.device:
            self._pending_format = None

        self.device = device
        self._bind_native_controls(selected_device)

        if self.device is None:
            logger.warning(
                "Failed to create camera. Need to get camera from available devices"
            )

        # The session of a stopped libcamera camera takes no other camera:
        # the pending rebuild builds the new stack for this device.
        if self.rebuild_pending:
            self._rebuild_format = None

            return

        # Qt builds a libcamera camera's libcamerasrc in here.
        with libcamera_gst_element.capture_new_elements():
            self.camera = None if self.device is None else QCamera(self.device)
            self.session.setCamera(self.camera)

    def unbind(self):
        self.device = None

        self._restart_due = False

        if self._control_restart_timer is not None:
            self._control_restart_timer.stop()

        self._pending_format = None
        self.directshow_controls = None
        self.image_controls = None

        # A pending rebuild builds an empty session instead.
        if self.rebuild_pending:
            self._start_after_rebuild = False
        else:
            self.session.setCamera(None)

        self.camera = None

    def _bind_native_controls(self, selected_device):
        """Bind the platform controls Qt has no API for (see the module
        docstring)."""
        self.directshow_controls = None
        self.image_controls = None

        if self.device is None:
            return

        description = self.device.description()

        if any(name in description for name in NATIVE_CAMERA_PROPERTIES_EXCLUDED):
            logger.info(f"No native camera properties for {description}")

            return

        directshow = open_directshow_camera_controls(self.device.id())
        self.directshow_controls = directshow

        if directshow is not None:
            self.image_controls = directshow
        # Loaded here, after the camera listing loaded Qt's GStreamer
        # backend (see libcamera_gst_element).
        elif description.startswith(LIBCAMERA_ID_PREFIX) and (
            libcamera_gst_element.load_libcamera_element_hook()
        ):
            self.image_controls = LibcameraImageControls()
        elif isinstance(selected_device, LinuxCameraDeviceContainer) and (
            selected_device.device_path
        ):
            self.image_controls = V4l2ImageControls(
                device_path=selected_device.device_path
            )

    # ------------------------------------------------------------------ #
    # Streaming and formats                                                #
    # ------------------------------------------------------------------ #
    def has_camera(self):
        return bool(self.camera)

    def is_active(self):
        # Until the rebuild, the requested state stands in for the camera's.
        if self.rebuild_pending:
            return self._start_after_rebuild

        return self.has_camera() and self.camera.isActive()

    def start(self):
        if self.rebuild_pending:
            self._start_after_rebuild = True

            return

        self._start_camera()

    def _start_camera(self):
        """Start the camera; a held libcamera format follows once the
        stream has settled (see _apply_pending_format)."""
        self._frame_since_start = False
        self.camera.start()
        camera = self.camera

        # Armed from the start, not from a frame: a camera started on a
        # format its output cannot play never delivers one.
        if self._pending_format is not None:
            QTimer.singleShot(
                PENDING_FORMAT_DELAY_MS,
                self.video_item,
                lambda: self._apply_pending_format(camera),
            )

        if self.is_libcamera():
            QTimer.singleShot(
                LIBCAMERA_FIRST_FRAME_TIMEOUT_MS,
                self.video_item,
                lambda: self._check_first_frame(camera),
            )

    def _check_first_frame(self, camera):
        """Log a started ``camera`` that has delivered no frame."""
        if camera is not self.camera or not camera.isActive():
            return

        if self._frame_since_start:
            return

        logger.error(
            f"No frames from {self.device.description()} "
            f"{LIBCAMERA_FIRST_FRAME_TIMEOUT_MS / 1000:g} s after start; "
            f"the camera must be re-selected"
        )

    def stop(self):
        if self.rebuild_pending:
            self._start_after_rebuild = False

            return

        self.camera.stop()

        if not self.is_libcamera():
            return

        self._stopped_camera = self.camera
        self._rebuild_format = self.camera.cameraFormat()
        self._start_after_rebuild = False
        self.rebuild_pending = True

        # Releases the stream's last frame, and blanks the preview.
        self._clear_preview_frame()

        # Torn down on the next event-loop pass: inside the stop's own
        # callback the teardown aborts. The video item as context drops the
        # teardown and rebuild if the panel is destroyed first.
        QTimer.singleShot(0, self.video_item, self._teardown_libcamera_stack)

    def _clear_preview_frame(self):
        self.video_item.videoSink().setVideoFrame(QVideoFrame())

    def _teardown_libcamera_stack(self):
        """Discard the stopped libcamera camera with its session and sink;
        the new stack is built once Qt has destroyed them."""
        if not self.rebuild_pending:
            return

        self.session.setCamera(None)

        for stale_object in (self._stopped_camera, self.session, self.sink):
            stale_object.deleteLater()

        # Recorders must not hold the old session or sink across this; the
        # widget builds a new recorder at every recording start.
        self._stopped_camera = None
        self.session = None
        self.sink = None

        QTimer.singleShot(
            LIBCAMERA_REBUILD_GAP_MS, self.video_item, self._rebuild_libcamera_stack
        )

    def _rebuild_libcamera_stack(self):
        """Build a fresh stack for the selected device, started if a start
        was requested meanwhile."""
        if not self.rebuild_pending:
            return

        # A frame queued from the capture thread may have landed after the
        # stop.
        self._clear_preview_frame()
        self.sink = QVideoSink()
        self.session = QMediaCaptureSession()
        self._wire_session()

        if self.device is not None:
            camera_format = self._rebuild_format

            # A camera that never had a format (a newly bound device) takes
            # the chosen one before its start: Qt's default can abort it.
            if camera_format is None or camera_format.isNull():
                camera_format, self._pending_format = self._pending_format, None

            # Qt builds the libcamerasrc in here.
            with libcamera_gst_element.capture_new_elements():
                self.camera = QCamera(self.device)

                if camera_format is not None and not camera_format.isNull():
                    self.camera.setCameraFormat(camera_format)

                self.session.setCamera(self.camera)

            if self._start_after_rebuild:
                self._start_camera()

        # Cleared before the callbacks, which may stop or start the camera.
        self._rebuild_format = None
        self._start_after_rebuild = False
        self.rebuild_pending = False
        callbacks, self._after_rebuild_callbacks = self._after_rebuild_callbacks, []

        for callback in callbacks:
            callback()

    def after_rebuild(self, callback):
        """Call ``callback`` once the pending libcamera rebuild has built
        the new session and sink."""
        self._after_rebuild_callbacks.append(callback)

    def video_formats(self):
        return self.device.videoFormats()

    def is_libcamera(self):
        return is_libcamera_device(self.device)

    def apply_format(self, camera_format):
        """Switch the camera to ``camera_format``: a libcamera camera takes
        it while streaming (see the module docstring), any other camera is
        stopped around the change."""
        if self.rebuild_pending:
            self._pending_format = camera_format

            return

        if self.is_libcamera():
            self._apply_libcamera_format(camera_format)

            return

        was_running = self.is_active()

        if was_running:
            self.camera.stop()
            QApplication.processEvents()

        self.camera.setCameraFormat(camera_format)

        if was_running:
            self.camera.start()

    def _apply_libcamera_format(self, camera_format):
        """Set ``camera_format`` while the camera streams, or on a camera
        that never had a format; otherwise hold it for the next start (see
        the module docstring)."""
        if self.camera.isActive() or self.camera.cameraFormat().isNull():
            self._pending_format = None
            self.camera.setCameraFormat(camera_format)

            return

        self._pending_format = camera_format

    def _apply_pending_format(self, camera):
        """Apply the held format once ``camera``'s stream has settled, as a
        user switching resolution while streaming would."""
        # A stop meanwhile replaced the camera or left it off: the format
        # stays held for the next start.
        if self._pending_format is None or camera is not self.camera:
            return

        if not camera.isActive():
            return

        camera.setCameraFormat(self._pending_format)
        self._pending_format = None

    # ------------------------------------------------------------------ #
    # Preview                                                              #
    # ------------------------------------------------------------------ #
    def _preview_frame_due(self):
        """Rate gate for frames forwarded to the display item (see
        CAMERA_PREVIEW_MAX_FPS). Recording is fed separately at full rate."""
        now = time.monotonic()

        if now - self._last_preview_frame_time < 1.0 / CAMERA_PREVIEW_MAX_FPS:
            return False

        self._last_preview_frame_time = now

        return True

    def forward_preview_frame(self, frame):
        # A late frame of a stopped libcamera stream must not be kept (see
        # the module docstring).
        if self.rebuild_pending:
            return

        self._frame_since_start = True

        if self._preview_frame_due():
            self.video_item.videoSink().setVideoFrame(frame)

    def forward_preview_image(self, image):
        """Show a provider feed's QImage in the display item."""
        if self._preview_frame_due():
            self.video_item.videoSink().setVideoFrame(QVideoFrame(image))

    # ------------------------------------------------------------------ #
    # Exposure and focus (ICameraDevice)                                   #
    # ------------------------------------------------------------------ #
    def supports_manual_exposure(self):
        return self.camera.isExposureModeSupported(QCamera.ExposureMode.ExposureManual)

    def set_auto_exposure(self):
        self.camera.setExposureMode(QCamera.ExposureMode.ExposureAuto)

    def set_manual_exposure(self, exposure_ms):
        self.camera.setExposureMode(QCamera.ExposureMode.ExposureManual)
        self.camera.setManualExposureTime(exposure_ms / 1000.0)

    def exposure_is_manual(self):
        return self.camera.exposureMode() == QCamera.ExposureMode.ExposureManual

    def exposure_time_ms(self):
        return self.camera.exposureTime() * 1000.0

    def manual_exposure_time_ms(self):
        return self.camera.manualExposureTime() * 1000.0

    def _directshow_focus(self):
        """The DirectShow focus control when Qt has no manual focus for the
        camera (Qt's Windows backend has none for any), else None."""
        directshow = self.directshow_controls

        if directshow is None or directshow.focus_span is None:
            return None

        if self.camera.isFocusModeSupported(QCamera.FocusMode.FocusModeManual):
            return None

        return directshow

    def supports_manual_focus(self):
        return self._directshow_focus() is not None or (
            self.camera.isFocusModeSupported(QCamera.FocusMode.FocusModeManual)
        )

    def set_auto_focus(self):
        directshow = self._directshow_focus()

        if directshow is not None:
            directshow.set_auto_focus()

            return

        self.camera.setFocusMode(QCamera.FocusMode.FocusModeAuto)

    def set_manual_focus(self, focus_distance):
        directshow = self._directshow_focus()

        if directshow is not None:
            directshow.set_focus_distance(focus_distance)

            return

        self.camera.setFocusMode(QCamera.FocusMode.FocusModeManual)
        self.camera.setFocusDistance(focus_distance)

    def focus_is_manual(self):
        directshow = self._directshow_focus()

        if directshow is None:
            return self.camera.focusMode() == QCamera.FocusMode.FocusModeManual

        # Read on every focus-row refresh, so an unplugged camera is logged
        # rather than raised into the observer.
        try:
            return not directshow.focus_is_auto()
        except RuntimeError as error:
            logger.error(f"Focus mode not read: {error}")

            return False

    def focus_distance(self):
        directshow = self._directshow_focus()

        if directshow is None:
            return self.camera.focusDistance()

        try:
            return directshow.focus_distance()
        except RuntimeError as error:
            logger.error(f"Focus distance not read: {error}")

            return self.camera.focusDistance()

    # ------------------------------------------------------------------ #
    # Image controls (ICameraDevice)                                       #
    # ------------------------------------------------------------------ #
    def image_control_ranges(self):
        if self.image_controls is None:
            return []

        return self.image_controls.ranges()

    def image_control(self, name):
        return self.image_controls.get(name)

    def set_image_control(self, name, value, auto=False):
        if not self.is_libcamera():
            self.image_controls.set(name, value, auto)

            return

        previous_value, previous_auto = self.image_controls.get(name)
        self.image_controls.set(name, value, auto)

        # Under auto the value is the algorithm's: only the mode counts.
        changed = auto != previous_auto or (not auto and value != previous_value)

        # A pending rebuild's new element takes the stored values anyway.
        if changed and self.is_active() and not self.rebuild_pending:
            self._schedule_control_restart()

    def _schedule_control_restart(self):
        """Restart the camera once a burst of image-control changes has
        settled (see LIBCAMERA_CONTROL_RESTART_DEBOUNCE_MS)."""

        if self._control_restart_timer is None:
            # Parented to the video item, so a destroyed panel drops it.
            timer = QTimer(self.video_item)
            timer.setSingleShot(True)
            timer.setInterval(LIBCAMERA_CONTROL_RESTART_DEBOUNCE_MS)
            timer.timeout.connect(self._restart_for_image_controls)
            self._control_restart_timer = timer

        self._control_restart_timer.start()

    def _restart_for_image_controls(self):
        """Stop and start the camera: the rebuilt libcamerasrc takes the
        stored control values as it starts."""

        # A restart replaces the session and sink a recording writes from.
        if self.hold_restarts:
            self._restart_due = True

            return

        if self.is_active():
            self.stop()
            self.start()

    @observe("hold_restarts")
    def _restart_after_hold(self, event):
        """Run a control restart deferred while the hold was on."""

        if self.hold_restarts or not self._restart_due:
            return

        self._restart_due = False
        self._schedule_control_restart()

    def describe_image_control(self, name, value):
        return self.image_controls.describe(name, value)


def _qt_camera_device(selected_device):
    """The QCameraDevice ``selected_device`` stands for, or None."""
    if isinstance(selected_device, LinuxCameraDeviceContainer):
        selected_device = selected_device.camera_device

    if isinstance(selected_device, QCameraDevice):
        return selected_device

    return None

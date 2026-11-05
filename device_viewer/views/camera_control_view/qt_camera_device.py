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
(brightness, contrast, ...) over DirectShow or v4l2.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.qt.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QMediaCaptureSession,
    QVideoFrame,
    QVideoSink,
)
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem
from traits.api import Float, HasTraits, Instance, provides

# Microdrop utils imports.
from microdrop_utils.camera_image_controls import (
    ICameraImageControls,
    V4l2ImageControls,
)
from microdrop_utils.directshow_camera_controls import (
    DirectShowCameraControls,
    open_directshow_camera_controls,
)
from microdrop_utils.v4l2_fps_getter import (
    LinuxCameraDeviceContainer,
    is_libcamera_device,
)

# Local imports.
from ...consts import CAMERA_PREVIEW_MAX_FPS, NATIVE_CAMERA_PROPERTIES_EXCLUDED
from ...interfaces.i_camera_device import ICameraDevice

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(ICameraDevice)
class QtCameraDevice(HasTraits):
    """QCamera + QMediaCaptureSession, with the preview frame-rate cap."""

    #: Display item the (rate-capped) preview frames are forwarded to.
    video_item = Instance(QGraphicsVideoItem)

    #: The session's own sink: frames arrive here at full camera rate, which
    #: is what the FFmpeg recorder taps.
    sink = Instance(QVideoSink)

    #: The capture session the camera and the Qt recorder are attached to.
    session = Instance(QMediaCaptureSession, ())

    #: The bound camera; None until a camera is selected.
    camera = Instance(QCamera)

    #: The bound camera's DirectShow controls (Windows); None elsewhere or
    #: for a camera without any.
    directshow_controls = Instance(DirectShowCameraControls)

    #: The bound camera's image controls; None for a camera without any.
    image_controls = Instance(ICameraImageControls)

    #: monotonic() time of the last frame forwarded to the display item.
    _last_preview_frame_time = Float(0.0)

    def traits_init(self):
        # The sink's videoFrameChanged is connected by the owning widget, not
        # here: frames arrive on the capture thread, and only a QObject
        # receiver gets them queued onto the GUI thread.
        self.session.setVideoSink(self.sink)

    # ------------------------------------------------------------------ #
    # Binding                                                              #
    # ------------------------------------------------------------------ #
    def bind(self, selected_device):
        """Bind a camera built from a LinuxCameraDeviceContainer (which
        carries V4L2 metadata) or a QCameraDevice; unknown devices leave
        the session without a camera."""
        self.camera = self._camera_from_device(selected_device)
        self.session.setCamera(self.camera)
        self._bind_native_controls(selected_device)

    def unbind(self):
        self.camera = None
        self.session.setCamera(None)
        self.directshow_controls = None
        self.image_controls = None

    def _bind_native_controls(self, selected_device):
        """Bind the platform controls Qt has no API for (see the module
        docstring)."""
        self.directshow_controls = None
        self.image_controls = None

        if self.camera is None:
            return

        description = self.camera.cameraDevice().description()

        if any(name in description for name in NATIVE_CAMERA_PROPERTIES_EXCLUDED):
            logger.info(f"No native camera properties for {description}")

            return

        directshow = open_directshow_camera_controls(self.camera.cameraDevice().id())
        self.directshow_controls = directshow

        if directshow is not None:
            self.image_controls = directshow
        elif isinstance(selected_device, LinuxCameraDeviceContainer) and (
            selected_device.device_path
        ):
            self.image_controls = V4l2ImageControls(
                device_path=selected_device.device_path
            )

    @staticmethod
    def _camera_from_device(selected_device):
        device = selected_device

        if isinstance(selected_device, LinuxCameraDeviceContainer):
            device = selected_device.camera_device

        if isinstance(device, QCameraDevice):
            return QCamera(selected_device)

        logger.warning(
            "Failed to create camera. Need to get camera from available devices"
        )

        return None

    # ------------------------------------------------------------------ #
    # Streaming and formats                                                #
    # ------------------------------------------------------------------ #
    def has_camera(self):
        return bool(self.camera)

    def is_active(self):
        return self.has_camera() and self.camera.isActive()

    def start(self):
        self.camera.start()

    def stop(self):
        self.camera.stop()

    def video_formats(self):
        return self.camera.cameraDevice().videoFormats()

    def is_libcamera(self):
        return is_libcamera_device(self.camera.cameraDevice())

    def set_format(self, camera_format):
        self.camera.setCameraFormat(camera_format)

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
        self.image_controls.set(name, value, auto)

    def describe_image_control(self, name, value):
        return self.image_controls.describe(name, value)

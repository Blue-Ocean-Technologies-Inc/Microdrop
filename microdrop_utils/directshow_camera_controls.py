# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Lens focus and image controls over DirectShow, for what Qt's Windows
backend cannot drive.

Qt Multimedia on Windows reports no manual focus and has no image controls
at all, although UVC cameras expose both through DirectShow's
IAMCameraControl and IAMVideoProcAmp, which work alongside Qt's Media
Foundation stream. The camera is matched to its DirectShow filter by device
instance: Qt's camera id and DirectShow's DevicePath name the same USB
interface, under different interface classes.
"""

# Standard library imports.
import sys

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Int, Tuple, Union, provides

# Microdrop utils imports.
from microdrop_utils.camera_image_controls import (
    EXPOSURE_CONTROL,
    IMAGE_CONTROL_LABELS,
    ICameraImageControls,
    ImageControlRange,
    format_exposure_ms,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(ICameraImageControls)
class DirectShowCameraControls(HasTraits):
    """One camera's DirectShow focus and image controls.

    Focus distance runs 0.0 (near) to 1.0 (far) over the camera's focus
    range, as UVC orders it (higher is farther).
    """

    #: The camera filter's IAMCameraControl COM pointer; None without one.
    camera_control = Any()

    #: The camera filter's IAMVideoProcAmp COM pointer; None without one.
    video_proc_amp = Any()

    #: (min, max) of the focus position; None without manual focus.
    focus_span = Union(None, Tuple(Int(), Int()))

    #: The camera has continuous auto focus.
    has_auto_focus = Bool(False)

    # ------------------------------------------------------------------ #
    # Focus                                                                #
    # ------------------------------------------------------------------ #
    def focus_is_auto(self):
        """Return whether continuous auto focus drives the lens."""
        from .directshow_com import CAMERA_CONTROL_FLAGS_AUTO, CAMERA_CONTROL_FOCUS

        _position, flags = self._call(self.camera_control.Get, CAMERA_CONTROL_FOCUS)

        return bool(flags & CAMERA_CONTROL_FLAGS_AUTO)

    def focus_distance(self):
        """Return the lens's focus distance, 0.0 (near) to 1.0 (far)."""
        from .directshow_com import CAMERA_CONTROL_FOCUS

        position, _flags = self._call(self.camera_control.Get, CAMERA_CONTROL_FOCUS)
        near, far = self.focus_span

        return min(max((position - near) / (far - near), 0.0), 1.0)

    def set_focus_distance(self, focus_distance):
        """Switch to manual focus at ``focus_distance`` (0.0 near, 1.0 far)."""
        from .directshow_com import CAMERA_CONTROL_FLAGS_MANUAL, CAMERA_CONTROL_FOCUS

        near, far = self.focus_span
        position = round(near + focus_distance * (far - near))

        self._call(
            self.camera_control.Set,
            CAMERA_CONTROL_FOCUS,
            position,
            CAMERA_CONTROL_FLAGS_MANUAL,
        )

    def set_auto_focus(self):
        """Switch to continuous auto focus, where the camera has it."""
        from .directshow_com import CAMERA_CONTROL_FLAGS_AUTO, CAMERA_CONTROL_FOCUS

        if not self.has_auto_focus:
            return

        position, _flags = self._call(self.camera_control.Get, CAMERA_CONTROL_FOCUS)

        self._call(
            self.camera_control.Set,
            CAMERA_CONTROL_FOCUS,
            position,
            CAMERA_CONTROL_FLAGS_AUTO,
        )

    # ------------------------------------------------------------------ #
    # Image controls (ICameraImageControls)                                #
    # ------------------------------------------------------------------ #
    def ranges(self):
        import comtypes

        from .directshow_com import (
            CAMERA_CONTROL_FLAGS_AUTO,
            CAMERA_CONTROL_FLAGS_MANUAL,
        )

        ranges = []

        for name in IMAGE_CONTROL_LABELS:
            interface, property_id = self._property(name)

            if interface is None:
                continue

            # A property the camera lacks fails GetRange.
            try:
                low, high, step, default, caps = interface.GetRange(property_id)
            except comtypes.COMError:
                continue

            if not caps & CAMERA_CONTROL_FLAGS_MANUAL or low >= high:
                continue

            ranges.append(
                ImageControlRange(
                    name=name,
                    low=low,
                    high=high,
                    step=max(step, 1),
                    default=default,
                    has_auto=bool(caps & CAMERA_CONTROL_FLAGS_AUTO),
                )
            )

        return ranges

    def get(self, name):
        from .directshow_com import CAMERA_CONTROL_FLAGS_AUTO

        interface, property_id = self._property(name)
        value, flags = self._call(interface.Get, property_id)

        return value, bool(flags & CAMERA_CONTROL_FLAGS_AUTO)

    def set(self, name, value, auto=False):
        from .directshow_com import (
            CAMERA_CONTROL_FLAGS_AUTO,
            CAMERA_CONTROL_FLAGS_MANUAL,
        )

        interface, property_id = self._property(name)
        flags = CAMERA_CONTROL_FLAGS_AUTO if auto else CAMERA_CONTROL_FLAGS_MANUAL

        self._call(interface.Set, property_id, int(value), flags)

    def describe(self, name, value):
        # DirectShow exposure is log2 seconds: -11 is 2^-11 s, about 0.49 ms.
        if name == EXPOSURE_CONTROL:
            return format_exposure_ms(2.0**value * 1000)

        return ""

    def _property(self, name):
        """The (COM interface, property id) of control ``name``: exposure
        is a camera control, the rest video proc amp properties; the
        interface is None when the camera lacks it."""
        from .directshow_com import CAMERA_CONTROL_EXPOSURE, VIDEO_PROC_AMP_PROPERTIES

        if name == EXPOSURE_CONTROL:
            return self.camera_control, CAMERA_CONTROL_EXPOSURE

        return self.video_proc_amp, VIDEO_PROC_AMP_PROPERTIES[name]

    @staticmethod
    def _call(method, *args):
        """Call a COM method, raising RuntimeError for its COMError (an
        unplugged camera, a rejected value)."""
        import comtypes

        try:
            return method(*args)
        except comtypes.COMError as error:
            raise RuntimeError(f"DirectShow camera control failed: {error}") from error


def _device_instance(device_path):
    """The USB device-interface instance a Windows device path names, without
    its interface class: ``\\\\?\\usb#vid_32e4&pid_0415&mi_00#7&1d2f&2&0000``
    for both Qt's ``...#{e5323777-...}\\global`` and DirectShow's
    ``...#{65e8773d-...}\\global``."""
    return device_path.rsplit("#{", 1)[0].lower()


def open_directshow_camera_controls(qt_device_id):
    """Return the DirectShow controls of the camera whose Qt
    ``QCameraDevice.id()`` is ``qt_device_id`` (bytes), or None: off
    Windows, without comtypes, or for a camera with neither camera controls
    (focus, exposure) nor image controls."""

    if sys.platform != "win32":
        return None

    try:
        import comtypes
        from comtypes.automation import VARIANT
        from comtypes.persist import IPropertyBag

        from .directshow_com import (
            CAMERA_CONTROL_FLAGS_AUTO,
            CAMERA_CONTROL_FLAGS_MANUAL,
            CAMERA_CONTROL_FOCUS,
            CLSID_SYSTEM_DEVICE_ENUM,
            CLSID_VIDEO_INPUT_DEVICE_CATEGORY,
            IAMCameraControl,
            IAMVideoProcAmp,
            ICreateDevEnum,
        )
    except ImportError:
        logger.info("comtypes is not installed: no camera properties on Windows")

        return None

    wanted = _device_instance(bytes(qt_device_id).decode(errors="replace"))

    try:
        device_enum = comtypes.CoCreateInstance(
            CLSID_SYSTEM_DEVICE_ENUM, interface=ICreateDevEnum
        )
        monikers = device_enum.CreateClassEnumerator(
            CLSID_VIDEO_INPUT_DEVICE_CATEGORY, 0
        )
    except comtypes.COMError as error:
        logger.warning(f"DirectShow camera enumeration failed: {error}")

        return None

    # S_FALSE with no enumerator: there are no video capture devices.
    if not monikers:
        return None

    while True:
        moniker, fetched = monikers.Next(1)

        if not fetched:
            return None

        # Virtual cameras (OBS, ...) have no DevicePath.
        try:
            properties = moniker.BindToStorage(
                None, None, IPropertyBag._iid_
            ).QueryInterface(IPropertyBag)
            device_path = properties.Read("DevicePath", VARIANT(), None)
        except comtypes.COMError:
            continue

        if _device_instance(device_path) == wanted:
            break

    try:
        camera_filter = moniker.BindToObject(None, None, comtypes.IUnknown._iid_)
    except comtypes.COMError as error:
        logger.warning(f"DirectShow filter for {device_path} failed: {error}")

        return None

    controls = DirectShowCameraControls()

    # Either interface may be missing; a camera without focus raises on the
    # focus GetRange, but may still have exposure.
    try:
        controls.camera_control = camera_filter.QueryInterface(IAMCameraControl)
        near, far, _step, _default, caps = controls.camera_control.GetRange(
            CAMERA_CONTROL_FOCUS
        )
    except comtypes.COMError:
        pass
    else:
        if caps & CAMERA_CONTROL_FLAGS_MANUAL and near < far:
            controls.focus_span = (near, far)
            controls.has_auto_focus = bool(caps & CAMERA_CONTROL_FLAGS_AUTO)

    try:
        controls.video_proc_amp = camera_filter.QueryInterface(IAMVideoProcAmp)
    except comtypes.COMError:
        pass

    if controls.camera_control is None and controls.video_proc_amp is None:
        return None

    logger.info(
        f"DirectShow controls for {device_path}: focus span "
        f"{controls.focus_span}, image controls "
        f"{controls.video_proc_amp is not None}"
    )

    return controls

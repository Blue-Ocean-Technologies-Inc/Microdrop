# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the device viewer's camera panel.

The Qt objects (QCamera, QMediaCaptureSession, recorders) stay in the view
layer; these models hold only what the controller decides on.
"""

# Enthought library imports.
from traits.api import (
    Bool,
    Float,
    HasTraits,
    Instance,
    Int,
    Range,
    Str,
    Tuple,
    Union,
)


class RecordingModel(HasTraits):
    """State of the current (or last) video recording."""

    #: True from a successful recording start until the file is finalized.
    active = Bool(False)

    #: Whether the camera was already on when the recording started; the
    #: camera is switched back off after the recording when it was not.
    camera_was_on = Bool(True)

    #: Link the finished recording in the status bar.
    show_status_message = Bool(True)

    #: File the current (or last) recording writes to.
    output_path = Str()


class CameraFocusModel(HasTraits):
    """The selected camera's focus, as the camera panel's focus row shows it."""

    #: Focus can be set: Qt drives manual focus, or a v4l2 focus device
    #: has a ``focus_absolute`` control.
    available = Bool(False)

    #: The camera has continuous auto focus to return to; a Pi CSI
    #: camera's lens (libcamera's own auto focus is disabled) does not.
    auto_available = Bool(False)

    #: Continuous auto focus drives the camera.
    auto = Bool(True)

    #: Focus distance, 0.0 (near) to 1.0 (far).
    distance = Range(0.0, 1.0, 0.5)

    #: Raw ``focus_absolute`` position under the v4l2 fallback; None while
    #: Qt drives the focus.
    raw_position = Union(None, Int)


class CameraModel(HasTraits):
    """Selected source, live state, format and exposure/focus fallbacks."""

    #: Combo label of the selected source (camera description, provider
    #: label, or empty for "<No Camera>").
    selected_camera = Str()

    #: The selected source is a CAMERA_SOURCES provider feed, not a QCamera.
    provider_selected = Bool(False)

    #: A provider feed is open and streaming into the panel.
    provider_feed_active = Bool(False)

    #: The panel's camera toggle is on (a QCamera or provider feed is live).
    camera_active = Bool(False)

    #: A protocol run holds the camera on (a select_source request with
    #: active=True): DEVICE_VIEWER_CAMERA_ACTIVE "false" requests are ignored
    #: until the next select_source request or the run's end.
    camera_leased = Bool(False)

    #: Why the provider feed last failed to open or stopped with an error;
    #: cleared when a feed opens.
    feed_error = Str()

    #: ``/dev/videoN`` node of the selected camera (Linux only), which the
    #: v4l2 exposure fallback drives; None elsewhere.
    v4l2_device_path = Union(None, Str)

    #: Selected camera format's resolution as (width, height).
    resolution = Tuple(Int(), Int())

    #: Selected camera format's max frame rate (0.0 when unknown).
    frame_rate = Float(0.0)

    #: Path of the last image capture written to disk.
    last_capture_path = Str()

    #: Node the v4l2 manual-focus fallback drives for the selected camera:
    #: its ``/dev/videoN`` node, or a libcamera camera's lens sub-device.
    v4l2_focus_device_path = Union(None, Str)

    #: v4l2 node the manual-focus fallback last drove; None while Qt (or
    #: continuous auto focus) drives the focus.
    v4l2_focus_path = Union(None, Str)

    #: Cached ``focus_absolute`` (min, max) of ``v4l2_focus_device_path``.
    v4l2_focus_range = Union(None, Tuple(Int(), Int()))

    #: ``v4l2_focus_device_path`` has continuous auto focus
    #: (``focus_automatic_continuous``); a bare lens sub-device does not.
    v4l2_focus_has_auto = Bool(False)

    #: The selected camera's focus, for the camera panel.
    focus = Instance(CameraFocusModel, ())

    #: v4l2 node the auto-exposure fallback last switched to auto; None while
    #: Qt (or manual exposure) drives the camera's exposure.
    v4l2_auto_exposure_path = Union(None, Str)

    #: The current (or last) recording.
    recording = Instance(RecordingModel, ())

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
from traits.api import Bool, Float, HasTraits, Instance, Int, Str, Tuple, Union


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


class CameraModel(HasTraits):
    """Selected source, live state, format and exposure/focus fallbacks."""

    #: Combo label of the selected source (camera description, provider
    #: label, or empty for "<No Camera>").
    selected_camera = Str()

    #: The selected source is a CAMERA_SOURCES provider feed, not a QCamera.
    provider_selected = Bool(False)

    #: A provider feed is open and streaming into the panel.
    provider_feed_active = Bool(False)

    #: ``/dev/videoN`` node of the selected camera (Linux only), which the
    #: v4l2 exposure/focus fallbacks drive; None elsewhere.
    v4l2_device_path = Union(None, Str)

    #: Selected camera format's resolution as (width, height).
    resolution = Tuple(Int(), Int())

    #: Selected camera format's max frame rate (0.0 when unknown).
    frame_rate = Float(0.0)

    #: Path of the last image capture written to disk.
    last_capture_path = Str()

    #: v4l2 node the manual-focus fallback last drove; None while Qt (or
    #: continuous auto focus) drives the focus.
    v4l2_focus_path = Union(None, Str)

    #: Cached ``focus_absolute`` (min, max) of ``v4l2_focus_path``.
    v4l2_focus_range = Union(None, Tuple(Int(), Int()))

    #: v4l2 node the auto-exposure fallback last switched to auto; None while
    #: Qt (or manual exposure) drives the camera's exposure.
    v4l2_auto_exposure_path = Union(None, Str)

    #: The current (or last) recording.
    recording = Instance(RecordingModel, ())

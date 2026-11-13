# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Which camera an alignment was made with.

A camera is known by a stable id where its backend gives one and by its
label (what the camera list shows) always. Two cameras are the same when
their ids are equal; when either has no id, when their labels are. So two
identical cameras — same label, different ids — stay apart, while a camera
whose backend gives no id is still recognised by name.

The Qt lookups (``QCameraDevice.id()``) stay at the edge; this module only
normalises what they return."""

# Standard library imports.
import os
from pathlib import Path

# Enthought library imports.
from traits.api import Bool, HasTraits, Property, Str

# Local imports.
from ..consts import CAMERA_MATCHED_BY_NAME_NOTE, V4L2_BY_PATH_DIR


def normalise_camera_id(raw_id):
    """Return a backend's camera id in the form presets keep.

    A Windows device-interface path (``\\\\?\\usb#vid_…#{class-guid}\\global``)
    loses its interface-class suffix and case, so the same USB device
    matches whichever capture API reported it. A bare number is an
    enumeration index (Qt's GStreamer backend reports one), not an
    identity: it becomes "". Other ids are only stripped.
    """
    camera_id = raw_id.strip()

    if camera_id.isdigit():
        return ""

    if camera_id.startswith("\\\\?\\"):
        return camera_id.rsplit("#{", 1)[0].lower()

    return camera_id


def v4l2_stable_camera_id(device_path, by_path_dir=V4L2_BY_PATH_DIR):
    """Return the udev ``by-path`` name of the V4L2 node ``device_path``
    (stable for one USB port across reboots and re-plugs), or "" when no
    link names it — ``/dev/videoN`` itself is renumbered at every boot."""
    by_path_dir = Path(by_path_dir)

    if not device_path or not by_path_dir.is_dir():
        return ""

    target = os.path.realpath(device_path)

    for link in sorted(by_path_dir.iterdir()):
        if os.path.realpath(link) == target:
            return f"v4l2-by-path:{link.name}"

    return ""


class CameraIdentity(HasTraits):
    """A camera as alignments remember it. Qt-free."""

    #: The backend's stable id, normalised; "" when the backend gives none
    #: (provider sources, a V4L2 node without a udev link).
    camera_id = Str()

    #: What the camera list shows; "" for no camera.
    label = Str()

    #: Whether ``camera_id`` is known, so matching does not rely on the
    #: label.
    has_stable_id = Property(Bool, observe="camera_id")

    #: Whether this names a camera at all.
    is_known = Property(Bool, observe="camera_id, label")

    #: The label for the user, saying when the camera is matched by name.
    display_text = Property(Str, observe="camera_id, label")

    def _get_has_stable_id(self):
        return bool(self.camera_id)

    def _get_is_known(self):
        return bool(self.camera_id or self.label)

    def _get_display_text(self):

        if self.has_stable_id or not self.label:
            return self.label

        return f"{self.label} {CAMERA_MATCHED_BY_NAME_NOTE}"

    def matches(self, other):
        """Whether ``other`` is the same camera: equal ids when both have
        one, else equal (non-empty) labels."""

        if other is None:
            return False

        if self.camera_id and other.camera_id:
            return self.camera_id == other.camera_id

        return bool(self.label) and self.label == other.label

    def same_as(self, other):
        """Whether ``other`` carries exactly this id and label — a camera
        selection that changed nothing."""
        return (
            other is not None
            and self.camera_id == other.camera_id
            and self.label == other.label
        )

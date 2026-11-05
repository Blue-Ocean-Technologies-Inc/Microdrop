# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hardware-free tests for Linux camera discovery in ``v4l2_fps_getter``.

On a Raspberry Pi with libcamera installed, Qt's GStreamer backend lists the
CSI camera (via libcamera) next to the raw ISP/CSI kernel nodes. Qt's camera
list and ``v4l2-ctl`` are faked here — no hardware or binary required.
"""

# Standard library imports.
from types import SimpleNamespace

# Microdrop utils imports.
import microdrop_utils.v4l2_fps_getter as v4l2

LIBCAMERA_IMX708 = "/base/axi/pcie@1000120000/rp1/i2c@80000/imx708@1a"

LIST_DEVICES_OUTPUT = """rp1-cfe (platform:1f00128000.csi):
\t/dev/video0
\t/dev/video1
\t/dev/media0

pispbe (platform:1000880000.pisp_be):
\t/dev/video20
\t/dev/video21

rpi-hevc-dec (platform:rpi-hevc-dec):
\t/dev/video19
\t/dev/media1

DH Camera: DH Camera (usb-xhci-hcd.0-1):
\t/dev/video8
\t/dev/video9
"""


class FakeCameraDevice:
    """Stands in for a QCameraDevice."""

    def __init__(self, description, camera_id=b""):
        self._description = description
        self._id = camera_id

    def description(self):
        return self._description

    def id(self):
        return self._id


def test_real_linux_nodes_skip_pi_internal_devices(monkeypatch):
    monkeypatch.setattr(
        v4l2.subprocess, "check_output", lambda *args, **kwargs: LIST_DEVICES_OUTPUT
    )

    assert v4l2.get_real_linux_nodes() == [8]


def test_libcamera_device_is_recognised_by_description_or_id():
    assert v4l2.is_libcamera_device(FakeCameraDevice(LIBCAMERA_IMX708))
    assert v4l2.is_libcamera_device(
        FakeCameraDevice("imx708", LIBCAMERA_IMX708.encode())
    )
    assert not v4l2.is_libcamera_device(FakeCameraDevice("DH Camera", b"/dev/video8"))


def test_linux_video_inputs_hide_internal_nodes_and_pair_v4l2_cameras(monkeypatch):
    qt_cameras = [
        FakeCameraDevice(LIBCAMERA_IMX708, LIBCAMERA_IMX708.encode()),
        FakeCameraDevice("rp1-cfe"),
        FakeCameraDevice("pispbe"),
        FakeCameraDevice("DH Camera"),
    ]
    monkeypatch.setattr(
        v4l2, "QMediaDevices", SimpleNamespace(videoInputs=lambda: qt_cameras)
    )
    monkeypatch.setattr(v4l2, "get_real_linux_nodes", lambda: [8])
    monkeypatch.setattr(v4l2, "get_v4l2_all_fps", lambda device_path: {})
    monkeypatch.setattr(v4l2, "find_v4l2_focus_subdevice", lambda: "/dev/v4l-subdev3")

    cameras = v4l2.get_linux_video_inputs()

    assert [camera.camera_device.description() for camera in cameras] == [
        LIBCAMERA_IMX708,
        "DH Camera",
    ]
    assert [camera.device_path for camera in cameras] == [None, "/dev/video8"]
    # The libcamera camera's focus goes through its lens sub-device.
    assert [camera.focus_device_path for camera in cameras] == [
        "/dev/v4l-subdev3",
        "/dev/video8",
    ]

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera panel's choice of a camera's stable id per backend (#963):
fakes stand in for QCameraDevice and the Linux camera container."""

# Standard library imports.
from types import SimpleNamespace

# Microdrop package imports.
from device_viewer.views.camera_control_view import widget
from device_viewer.views.camera_control_view.widget import CameraControlWidget


def _qt_camera(camera_id, description="Camera"):
    return SimpleNamespace(
        id=lambda: camera_id.encode(), description=lambda: description
    )


def test_a_plain_qt_camera_uses_qts_id():
    camera = _qt_camera("\\\\?\\usb#vid_1&pid_2#7&abc&0&0000#{guid}\\global")

    assert CameraControlWidget._stable_camera_id(camera, None) == (
        "\\\\?\\usb#vid_1&pid_2#7&abc&0&0000#{guid}\\global"
    )


def test_a_v4l2_camera_uses_its_by_path_link_checked_by_name(monkeypatch):
    calls = []

    def stable_id(device_path, expected_name=""):
        calls.append((device_path, expected_name))

        return "v4l2-by-path:usb-port"

    monkeypatch.setattr(widget, "v4l2_stable_camera_id", stable_id)
    camera = _qt_camera("0", "DH Camera: DH Camera")
    container = SimpleNamespace(device_path="/dev/video0")

    assert CameraControlWidget._stable_camera_id(camera, container) == (
        "v4l2-by-path:usb-port"
    )
    assert calls == [("/dev/video0", "DH Camera: DH Camera")]


def test_a_libcamera_camera_uses_its_device_tree_path():
    camera = _qt_camera("/base/axi/pcie@120000/rp1/i2c@88000/imx708@1a")
    container = SimpleNamespace(device_path=None)

    assert CameraControlWidget._stable_camera_id(camera, container) == (
        "/base/axi/pcie@120000/rp1/i2c@88000/imx708@1a"
    )


def test_a_linux_camera_without_node_or_device_tree_path_has_no_id():
    container = SimpleNamespace(device_path=None)

    assert CameraControlWidget._stable_camera_id(_qt_camera("3"), container) == ""

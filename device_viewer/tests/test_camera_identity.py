# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Camera identity (#963 stage 2): id normalisation, the V4L2 by-path
lookup, the id-then-label matching rule, and preset scope applicability."""

# Standard library imports.
import os
from pathlib import PurePosixPath

# Microdrop package imports.
from device_viewer.models import camera_identity
from device_viewer.models.alignment_preset import (
    AlignmentPreset,
    alignment_scope_error,
)
from device_viewer.models.camera_identity import (
    CameraIdentity,
    normalise_camera_id,
    v4l2_stable_camera_id,
)

QUAD = [[0.0, 0.0], [100.0, 0.0], [100.0, 80.0], [0.0, 80.0]]

#: What Qt's Media Foundation backend reports on Windows (checked live).
WINDOWS_QT_ID = (
    "\\\\?\\usb#vid_32e4&pid_4802&mi_00#7&1de8b77c&4&0000"
    "#{e5323777-f976-4f5b-9b55-b94699c46e44}\\global"
)


def test_windows_ids_lose_the_interface_class_and_case():
    assert normalise_camera_id(WINDOWS_QT_ID) == (
        "\\\\?\\usb#vid_32e4&pid_4802&mi_00#7&1de8b77c&4&0000"
    )
    assert normalise_camera_id(WINDOWS_QT_ID.upper()) == normalise_camera_id(
        WINDOWS_QT_ID
    )


def test_a_bare_index_is_no_identity():
    # Qt's GStreamer backend on the Pi reports "0", "1", ... (checked live).
    assert normalise_camera_id("0") == ""
    assert normalise_camera_id(" 12 ") == ""


def test_other_ids_are_only_stripped():
    assert normalise_camera_id(" /base/axi/pcie@120000/rp1/i2c@88000/imx708@1a ") == (
        "/base/axi/pcie@120000/rp1/i2c@88000/imx708@1a"
    )


def test_v4l2_by_path_names_the_node(tmp_path, monkeypatch):
    # The links of a Pi's DH camera (checked live); names with ':' cannot
    # be created on Windows, so the directory listing is faked.
    targets = {
        "platform-xhci-hcd.1-usbv2-0:2:1.0-video-index0": "/dev/video0",
        "platform-xhci-hcd.1-usb-0:2:1.0-video-index0": "/dev/video0",
        "platform-1000800000.codec-video-index0": "/dev/video19",
    }
    links = [PurePosixPath("/dev/v4l/by-path") / name for name in targets]

    def realpath(path):
        return targets.get(os.path.basename(str(path)), str(path))

    monkeypatch.setattr(camera_identity.Path, "is_dir", lambda self: True)
    monkeypatch.setattr(camera_identity.Path, "iterdir", lambda self: iter(links))
    monkeypatch.setattr(camera_identity.os.path, "realpath", realpath)

    # Both links name the node; the first by name is chosen every time.
    assert v4l2_stable_camera_id("/dev/video0", tmp_path) == (
        "v4l2-by-path:platform-xhci-hcd.1-usb-0:2:1.0-video-index0"
    )
    assert v4l2_stable_camera_id("/dev/video7", tmp_path) == ""


def test_v4l2_node_paired_with_another_camera_has_no_id(tmp_path, monkeypatch):
    # The node's own card name (sysfs) must be the Qt camera's
    # description; otherwise the enumeration-order pairing is wrong.
    sysfs = tmp_path / "video4linux"
    (sysfs / "video0").mkdir(parents=True)
    (sysfs / "video0" / "name").write_text("DH Camera: DH Camera\n")
    by_path = tmp_path / "by-path"
    by_path.mkdir()
    (by_path / "usb-port-video-index0").write_text("")

    monkeypatch.setattr(
        camera_identity.os.path,
        "realpath",
        lambda path: "/dev/video0" if "usb-port" in str(path) else str(path),
    )

    def stable_id(expected_name):
        return v4l2_stable_camera_id(
            "/dev/video0", by_path, expected_name=expected_name, sysfs_dir=sysfs
        )

    assert stable_id("DH Camera: DH Camera") == "v4l2-by-path:usb-port-video-index0"
    assert stable_id("USB 2.0 Camera") == ""


def test_v4l2_without_udev_links_has_no_id(tmp_path):
    assert v4l2_stable_camera_id("/dev/video0", tmp_path / "missing") == ""
    assert v4l2_stable_camera_id(None, tmp_path) == ""


def test_ids_decide_when_both_cameras_have_one():
    left = CameraIdentity(camera_id="usb#a", label="USB Camera")
    right = CameraIdentity(camera_id="usb#b", label="USB Camera")

    # Two identical cameras on different ports stay apart.
    assert not left.matches(right)
    assert left.matches(CameraIdentity(camera_id="usb#a", label="Renamed"))


def test_labels_decide_when_either_camera_has_no_id():
    with_id = CameraIdentity(camera_id="usb#a", label="USB Camera")
    by_name = CameraIdentity(label="USB Camera")

    assert with_id.matches(by_name)
    assert by_name.matches(with_id)
    assert not by_name.matches(CameraIdentity(label="Other"))
    assert not CameraIdentity().matches(CameraIdentity())
    assert not by_name.matches(None)


def test_display_text_says_when_a_camera_is_matched_by_name():
    assert CameraIdentity(camera_id="x", label="Cam").display_text == "Cam"
    assert "matched by name" in CameraIdentity(label="Cam").display_text
    assert CameraIdentity().display_text == ""


def test_same_as_needs_identical_id_and_label():
    camera = CameraIdentity(camera_id="x", label="Cam")

    assert camera.same_as(CameraIdentity(camera_id="x", label="Cam"))
    assert not camera.same_as(CameraIdentity(camera_id="y", label="Cam"))
    assert not camera.same_as(CameraIdentity(camera_id="x", label="Cam 2"))


def _preset(scope, device_key="chip-a", camera_id="usb#a", label="Cam"):
    return AlignmentPreset(
        scope=scope,
        device_key=device_key,
        camera_id=camera_id,
        camera_label=label,
        scene_quad=QUAD,
        endpoint_quad=QUAD,
    )


def test_scope_decides_where_a_preset_applies():
    this_camera = CameraIdentity(camera_id="usb#a", label="Cam")
    twin_camera = CameraIdentity(camera_id="usb#b", label="Cam")

    camera_device = _preset("camera_device")
    device = _preset("device")
    camera = _preset("camera")

    assert camera_device.applies_to(this_camera, "chip-a")
    assert not camera_device.applies_to(twin_camera, "chip-a")
    assert not camera_device.applies_to(this_camera, "chip-b")

    assert device.applies_to(twin_camera, "chip-a")
    assert not device.applies_to(this_camera, "chip-b")

    assert camera.applies_to(this_camera, "chip-b")
    assert not camera.applies_to(twin_camera, "chip-a")


def test_scope_rules_for_saving():
    assert alignment_scope_error("device", "", "", False) == ""
    assert alignment_scope_error("camera_device", "", "", True)
    assert alignment_scope_error("camera_device", "Cam", "", False) == ""
    assert alignment_scope_error("camera", "Cam", "", False)
    assert alignment_scope_error("camera", "Cam", "", True) == ""
    assert alignment_scope_error("everywhere", "Cam", "x", True)


def test_preset_round_trips_its_camera_id():
    preset = _preset("camera_device")

    assert AlignmentPreset.from_dict(preset.to_dict()).camera_id == "usb#a"


def test_only_a_last_used_record_may_lack_an_endpoint():
    record = _preset("camera_device").to_dict()
    record["endpoint_quad"] = None

    try:
        AlignmentPreset.from_dict(record)
    except ValueError:
        pass
    else:
        raise AssertionError("a named preset without an endpoint was accepted")

    record["kind"] = "last_used"

    assert AlignmentPreset.from_dict(record).endpoint_quad is None

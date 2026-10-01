# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The perspective window's device-outline reference: device listing,
persistence through the preferences, and fitting into the frame."""

# Standard library imports.
import shutil

# Third-party imports.
import numpy as np
import pytest

# Microdrop package imports.
from device_viewer.consts import MASTER_SVG_FILE
from image_viewer.device_outline import DeviceOutlineReference
from image_viewer.preferences import ImageViewerPreferences

DEVICE_2X3_SVG = MASTER_SVG_FILE.parent / "2x3device.svg"


@pytest.fixture
def repo_dir(tmp_path):
    for name in ("b_device.svg", "a_device.svg"):
        shutil.copy(DEVICE_2X3_SVG, tmp_path / name)

    (tmp_path / "notes.txt").write_text("")

    return tmp_path


def test_lists_repo_devices_after_none(repo_dir):
    reference = DeviceOutlineReference(
        preferences=ImageViewerPreferences(), repo_dir=str(repo_dir)
    )

    assert reference.device_directory() == repo_dir
    assert sorted(reference.devices.values()) == [
        "000:None",
        "001:a_device",
        "002:b_device",
    ]
    assert reference.devices[""] == "000:None"
    assert reference.devices[str(repo_dir / "a_device.svg")] == "001:a_device"


def test_lists_every_svg_in_the_repo_not_only_seeded_ones(repo_dir):
    for name in ("90_pin_array.svg", "pin_map.svg", "Zika-4d Mirror (2).svg"):
        shutil.copy(DEVICE_2X3_SVG, repo_dir / name)

    reference = DeviceOutlineReference(
        preferences=ImageViewerPreferences(), repo_dir=str(repo_dir)
    )

    assert len(reference.devices) == 6
    assert reference.devices[str(repo_dir / "Zika-4d Mirror (2).svg")].endswith(
        ":Zika-4d Mirror (2)"
    )


def test_unset_repo_falls_back_to_bundled_devices():
    reference = DeviceOutlineReference(preferences=ImageViewerPreferences())

    assert reference.device_directory() == MASTER_SVG_FILE.parent


def test_missing_repo_falls_back_to_bundled_devices(tmp_path):
    reference = DeviceOutlineReference(
        preferences=ImageViewerPreferences(), repo_dir=str(tmp_path / "missing")
    )

    assert reference.device_directory() == MASTER_SVG_FILE.parent
    assert str(DEVICE_2X3_SVG) in reference.devices


def test_settings_load_from_and_persist_to_preferences(repo_dir):
    svg_path = str(repo_dir / "a_device.svg")
    preferences = ImageViewerPreferences(
        device_outline_svg=svg_path,
        device_outline_alpha=40,
        device_outline_color="#ff0000",
    )
    reference = DeviceOutlineReference(preferences=preferences, repo_dir=str(repo_dir))

    assert reference.svg_path == svg_path
    assert reference.alpha == 40
    assert reference.color == (1.0, 0.0, 0.0)

    reference.trait_set(svg_path="", alpha=75, color=(0.0, 1.0, 0.0))

    assert preferences.device_outline_svg == ""
    assert preferences.device_outline_alpha == 75
    assert preferences.device_outline_color == "#00ff00"


def test_unlisted_saved_device_draws_none(repo_dir, tmp_path):
    preferences = ImageViewerPreferences(
        device_outline_svg=str(tmp_path / "deleted.svg")
    )
    reference = DeviceOutlineReference(preferences=preferences, repo_dir=str(repo_dir))

    assert reference.svg_path == ""
    assert reference.polygons == []
    assert reference.outline_rings(640, 480) == []


def test_outline_fits_and_centres_in_frame(repo_dir):
    reference = DeviceOutlineReference(
        preferences=ImageViewerPreferences(), repo_dir=str(repo_dir)
    )
    reference.svg_path = str(repo_dir / "a_device.svg")

    rings = reference.outline_rings(400, 200)
    points = np.vstack(rings)

    assert len(rings) == 92

    # The 2x3 device is near square, so the frame's height limits it: it
    # spans the full height and is centred across the width.
    assert points[:, 1].min() == pytest.approx(0)
    assert points[:, 1].max() == pytest.approx(200)
    assert points[:, 0].min() + points[:, 0].max() == pytest.approx(400)

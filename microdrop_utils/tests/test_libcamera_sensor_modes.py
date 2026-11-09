# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hardware-free tests for ``libcamera_sensor_modes``: the listings are
real ``rpicam-hello --list-cameras`` output from a Pi 5 with a Camera
Module 3 (imx708), captured with the camera free and in use."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Microdrop utils imports.
import microdrop_utils.libcamera_sensor_modes as modes_module
from microdrop_utils.libcamera_sensor_modes import (
    KNOWN_SENSOR_MODES,
    SensorMode,
    libcamera_fps_for,
    parse_list_cameras,
    sensor_base_name,
)

IMX708_ID = "/base/axi/pcie@1000120000/rp1/i2c@88000/imx708@1a"

FREE_LISTING = f"""Available cameras
-----------------
0 : imx708_noir [4608x2592 10-bit RGGB] ({IMX708_ID})
    Modes: 'SRGGB10_CSI2P' : 1536x864 [120.13 fps - (768, 432)/3072x1728 crop]
                             2304x1296 [56.03 fps - (0, 0)/4608x2592 crop]
                             4608x2592 [14.35 fps - (0, 0)/4608x2592 crop]
"""

BUSY_LISTING = f"""Available cameras
-----------------
0 : imx708_noir [4608x2592 10-bit] ({IMX708_ID})
    Modes: 'SBGGR10_CSI2P' : 1536x864 [30.00 fps - (65519, 65511)/65535x65535 crop]
                             2304x1296 [30.00 fps - (65519, 65511)/65535x65535 crop]
                             4608x2592 [30.00 fps - (65519, 65511)/65535x65535 crop]
"""

IMX708_MODES = [
    SensorMode(1536, 864, 120.13),
    SensorMode(2304, 1296, 56.03),
    SensorMode(4608, 2592, 14.35),
]


@pytest.fixture(autouse=True)
def empty_cache(monkeypatch):
    """Each test starts without a cached listing."""
    monkeypatch.setattr(modes_module, "_cached_sensor_modes", {})


def test_parse_free_listing():
    assert parse_list_cameras(FREE_LISTING) == {IMX708_ID: IMX708_MODES}


def test_parse_rejects_busy_listing():
    assert parse_list_cameras(BUSY_LISTING) == {}


def test_parse_rejects_one_frame_rate_for_every_mode():
    listing = FREE_LISTING.replace("120.13", "30.00").replace("56.03", "30.00")

    assert parse_list_cameras(listing.replace("14.35", "30.00")) == {}


def test_parse_garbage():
    assert parse_list_cameras("") == {}
    assert parse_list_cameras("No cameras available!") == {}


@pytest.mark.parametrize(
    ("width", "height", "fps"),
    [
        (1536, 864, 120.13),
        (320, 240, 120.13),
        (1600, 1200, 56.03),
        (1920, 1080, 56.03),
        (2048, 1536, 14.35),
        (4608, 2592, 14.35),
        (9000, 9000, 14.35),
    ],
)
def test_fps_from_smallest_covering_mode(width, height, fps):
    assert libcamera_fps_for(width, height, IMX708_MODES) == fps


def test_fps_unknown_without_modes():
    assert libcamera_fps_for(1920, 1080, []) == 0.0


def test_sensor_base_name_strips_variant():
    assert sensor_base_name("imx708_noir") == "imx708"
    assert sensor_base_name("imx708_wide_noir") == "imx708"
    assert sensor_base_name("imx477") == "imx477"


def test_known_table_matches_listing():
    assert KNOWN_SENSOR_MODES["imx708"] == IMX708_MODES


def test_read_caches_first_good_listing(monkeypatch):
    listings = iter([FREE_LISTING, BUSY_LISTING])
    monkeypatch.setattr(
        modes_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=next(listings)),
    )

    assert modes_module.read_sensor_modes() == {IMX708_ID: IMX708_MODES}
    assert modes_module.read_sensor_modes() == {IMX708_ID: IMX708_MODES}


def test_device_falls_back_to_known_table(monkeypatch):
    monkeypatch.setattr(modes_module, "read_sensor_modes", lambda: {})
    monkeypatch.setattr(
        modes_module, "v4l2_subdevice_names", lambda: ["csi2", "imx708_noir"]
    )

    assert modes_module.sensor_modes_for_device("/base/unknown@10") == IMX708_MODES
    assert modes_module.sensor_modes_for_device(IMX708_ID) == IMX708_MODES


def test_device_unknown_sensor(monkeypatch):
    monkeypatch.setattr(modes_module, "read_sensor_modes", lambda: {})
    monkeypatch.setattr(modes_module, "v4l2_subdevice_names", lambda: ["ov5647"])

    assert modes_module.sensor_modes_for_device("/base/ov5647@36") == []

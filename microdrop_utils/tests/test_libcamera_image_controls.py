# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hardware-free tests for LibcameraImageControls: the slider mapping onto
libcamerasrc properties, with the element itself faked."""

# Third-party imports.
import pytest

# Microdrop utils imports.
import microdrop_utils.camera_image_controls as controls
from microdrop_utils.camera_image_controls import (
    EXPOSURE_CONTROL,
    IMAGE_CONTROL_LABELS,
    LibcameraImageControls,
)


class FakeElement:
    """Stands in for libcamera_gst_element: values set are kept and logged
    in order; live properties are what the element reports."""

    def __init__(self):
        self.exists = False
        self.stored = {}
        self.live = {}
        self.writes = []

    def set(self, name, value):
        self.stored[name] = value
        self.writes.append((name, value))


@pytest.fixture
def element(monkeypatch):
    fake = FakeElement()
    monkeypatch.setattr(controls, "has_element", lambda: fake.exists)
    monkeypatch.setattr(controls, "set_element_property", fake.set)
    monkeypatch.setattr(controls, "stored_element_property", fake.stored.get)
    monkeypatch.setattr(
        controls, "get_element_property", lambda name: fake.live.get(name, 0)
    )

    return fake


def test_ranges_follow_display_order_and_scale():
    ranges = LibcameraImageControls().ranges()
    names = [control.name for control in ranges]

    assert names == [name for name in IMAGE_CONTROL_LABELS if name in names]
    assert names == [
        EXPOSURE_CONTROL,
        "gain",
        "brightness",
        "contrast",
        "saturation",
        "sharpness",
    ]

    by_name = {control.name: control for control in ranges}

    assert (by_name["gain"].low, by_name["gain"].high) == (100, 1600)
    assert (by_name["brightness"].low, by_name["brightness"].high) == (-100, 100)
    assert by_name["contrast"].default == 100
    assert by_name[EXPOSURE_CONTROL].has_auto and by_name["gain"].has_auto
    assert not by_name["brightness"].has_auto


def test_describe_in_real_units():
    image_controls = LibcameraImageControls()

    assert image_controls.describe(EXPOSURE_CONTROL, 2000) == "2.00 ms"
    assert image_controls.describe("gain", 250) == "2.50"
    assert image_controls.describe("brightness", -80) == "-0.80"
    assert image_controls.describe("hue", 3) == ""


def test_manual_set_writes_mode_before_value(element):
    image_controls = LibcameraImageControls()
    image_controls.set(EXPOSURE_CONTROL, 40000)
    image_controls.set("gain", 800)

    assert element.writes == [
        ("exposure-time-mode", "manual"),
        ("exposure-time", 40000.0),
        ("analogue-gain-mode", "manual"),
        ("analogue-gain", 8.0),
    ]


def test_auto_set_switches_the_mode_only(element):
    LibcameraImageControls().set("gain", 800, auto=True)

    assert element.writes == [("analogue-gain-mode", "auto")]


def test_get_reports_defaults_then_values_set(element):
    image_controls = LibcameraImageControls()

    assert image_controls.get("contrast") == (100, False)
    assert image_controls.get("gain") == (100, True)

    image_controls.set("contrast", 30)
    image_controls.set("gain", 250)

    assert image_controls.get("contrast") == (30, False)
    assert image_controls.get("gain") == (250, False)


def test_values_set_outlive_the_controls_object(element):
    LibcameraImageControls().set("brightness", -40)

    assert LibcameraImageControls().get("brightness") == (-40, False)


def test_get_under_auto_reads_the_live_value(element):
    element.exists = True
    element.live = {"exposure-time": 9982, "analogue-gain": 1.28}
    image_controls = LibcameraImageControls()

    assert image_controls.get(EXPOSURE_CONTROL) == (9982, True)
    assert image_controls.get("gain") == (128, True)


def test_unknown_control_raises():
    with pytest.raises(RuntimeError):
        LibcameraImageControls().set("hue", 0)

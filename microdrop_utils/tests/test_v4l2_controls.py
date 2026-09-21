# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hardware-free tests for the v4l2 control helpers in ``v4l2_fps_getter``.

The Portable DropBot's GStreamer Qt Multimedia backend cannot drive manual
focus, so the camera control widget falls back to ``v4l2-ctl`` for the
camera's ``focus_absolute`` control. All ``v4l2-ctl`` calls are
monkeypatched here — no hardware or binary required.
"""

# Standard library imports.
from types import SimpleNamespace

# Microdrop utils imports.
import microdrop_utils.v4l2_fps_getter as v4l2

LIST_CTRLS_OUTPUT = """
                brightness 0x00980900 (int)  : min=-64 max=64 step=1 value=0
                  contrast 0x00980901 (int)  : min=0 max=95 step=1 value=0
             auto_exposure 0x009a0901 (menu) : min=0 max=3 default=0 value=1
       focus_absolute 0x009a090a (int)  : min=0 max=1023 step=1 value=450 flags=inactive
focus_automatic_continuous 0x009a090c (bool) : default=1 value=1
"""


# --- parse_v4l2_control_range ----------------------------------------------------


def test_parse_v4l2_control_range_found():
    assert v4l2.parse_v4l2_control_range(LIST_CTRLS_OUTPUT, "focus_absolute") == (
        0,
        1023,
    )


def test_parse_v4l2_control_range_absent():
    assert v4l2.parse_v4l2_control_range(LIST_CTRLS_OUTPUT, "zoom_absolute") is None


def test_parse_v4l2_control_range_menu_control_still_parses():
    # A "(menu)" control line still carries min/max, unlike a "(bool)" line.
    assert v4l2.parse_v4l2_control_range(LIST_CTRLS_OUTPUT, "auto_exposure") == (0, 3)


def test_parse_v4l2_control_range_bool_control_has_no_range():
    assert (
        v4l2.parse_v4l2_control_range(LIST_CTRLS_OUTPUT, "focus_automatic_continuous")
        is None
    )


# --- get_v4l2_control_range -------------------------------------------------------


def test_get_v4l2_control_range_builds_expected_argv(monkeypatch):
    captured = {}

    def _fake_run(args, **kwargs):
        captured["args"] = args

        return SimpleNamespace(stdout=LIST_CTRLS_OUTPUT)

    monkeypatch.setattr(v4l2.subprocess, "run", _fake_run)

    result = v4l2.get_v4l2_control_range("/dev/video2", "focus_absolute")

    assert captured["args"] == [
        "v4l2-ctl",
        "--device=/dev/video2",
        "--list-ctrls",
    ]
    assert result == (0, 1023)


def test_get_v4l2_control_range_missing_tool_returns_none(monkeypatch):
    def _fake_run(args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(v4l2.subprocess, "run", _fake_run)

    assert v4l2.get_v4l2_control_range("/dev/video2", "focus_absolute") is None


# --- set_v4l2_controls -------------------------------------------------------------


def test_set_v4l2_controls_builds_expected_argv_and_order(monkeypatch):
    captured = {}

    def _fake_run(args, **kwargs):
        captured["args"] = args

        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(v4l2.subprocess, "run", _fake_run)

    ok = v4l2.set_v4l2_controls(
        "/dev/video2", focus_automatic_continuous=0, focus_absolute=450
    )

    assert ok is True
    assert captured["args"] == [
        "v4l2-ctl",
        "--device=/dev/video2",
        "--set-ctrl=focus_automatic_continuous=0",
        "--set-ctrl=focus_absolute=450",
    ]


def test_set_v4l2_controls_false_on_failure(monkeypatch):
    def _fake_run(args, **kwargs):
        raise v4l2.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(v4l2.subprocess, "run", _fake_run)

    assert v4l2.set_v4l2_controls("/dev/video2", focus_absolute=450) is False


# --- get_v4l2_control --------------------------------------------------------------


def test_get_v4l2_control_builds_expected_argv_and_parses_value(monkeypatch):
    captured = {}

    def _fake_run(args, **kwargs):
        captured["args"] = args

        return SimpleNamespace(stdout="focus_absolute: 450\n")

    monkeypatch.setattr(v4l2.subprocess, "run", _fake_run)

    result = v4l2.get_v4l2_control("/dev/video2", "focus_absolute")

    assert captured["args"] == [
        "v4l2-ctl",
        "--device=/dev/video2",
        "--get-ctrl=focus_absolute",
    ]
    assert result == 450


def test_get_v4l2_control_none_on_failure(monkeypatch):
    def _fake_run(args, **kwargs):
        raise v4l2.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(v4l2.subprocess, "run", _fake_run)

    assert v4l2.get_v4l2_control("/dev/video2", "focus_absolute") is None

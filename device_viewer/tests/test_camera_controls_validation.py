# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the DV-side camera-controls handler's request validation (#703).

A malformed DEVICE_VIEWER_CAMERA_SET_CONTROLS payload must never reach the
camera widget -- it must be answered ok=False instead, so a requester
waiting on DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED (e.g. the portable
fluorescence capture routine) fails fast rather than timing out."""

# Standard library imports.
import json

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.views.device_view_dock_pane import parse_camera_controls_request


def test_valid_request_is_returned_as_a_dict():
    payload = {"request_id": "r1", "exposure_ms": 20.0, "focus_distance": 0.5}
    request, reply = parse_camera_controls_request(json.dumps(payload))

    assert reply is None
    assert request == payload


@pytest.mark.parametrize("message", [None, "", "   "])
def test_empty_message_validates_to_auto_controls(message):
    request, reply = parse_camera_controls_request(message)

    assert reply is None
    assert request == {
        "request_id": "",
        "exposure_ms": None,
        "hold_auto_exposure": False,
        "focus_distance": None,
    }


def test_bad_json_is_answered_ok_false_with_no_request_id():
    request, reply = parse_camera_controls_request("not json")

    assert request is None
    assert reply["ok"] is False
    assert reply["request_id"] == ""
    assert reply["error"]


def test_out_of_range_exposure_is_answered_ok_false():
    payload = {"request_id": "r1", "exposure_ms": -5}
    request, reply = parse_camera_controls_request(json.dumps(payload))

    assert request is None
    assert reply["ok"] is False
    assert reply["error"]


def test_request_id_is_recovered_into_the_failure_reply():
    payload = {"request_id": "keep-me", "focus_distance": 5.0}
    request, reply = parse_camera_controls_request(json.dumps(payload))

    assert request is None
    assert reply["ok"] is False
    assert reply["request_id"] == "keep-me"

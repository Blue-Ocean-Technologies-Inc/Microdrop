"""Tests for the in-process demo responder that fakes
DropletDetectionMixinService."""

import json
from unittest.mock import patch


def test_succeed_mode_returns_all_requested_channels(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DROPLETS_DETECTED, DETECT_DROPLETS

    captured = []
    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: captured.append((topic, message)),
    )

    r = DropletDetectionResponder(mode="succeed")
    r.listener_actor_routine(json.dumps([1, 2, 3]), DETECT_DROPLETS)

    assert len(captured) == 1
    topic, body = captured[0]
    assert topic == DROPLETS_DETECTED
    parsed = json.loads(body)
    assert parsed["success"] is True
    assert parsed["detected_channels"] == [1, 2, 3]
    assert parsed["error"] == ""


def test_drop_one_mode_drops_first_channel(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DETECT_DROPLETS

    captured = []
    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: captured.append((topic, message)),
    )

    r = DropletDetectionResponder(mode="drop_one")
    r.listener_actor_routine(json.dumps([3, 4, 5]), DETECT_DROPLETS)

    parsed = json.loads(captured[0][1])
    assert parsed["detected_channels"] == [4, 5]
    assert parsed["success"] is True


def test_drop_all_mode_returns_empty_list(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DETECT_DROPLETS

    captured = []
    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: captured.append((topic, message)),
    )

    r = DropletDetectionResponder(mode="drop_all")
    r.listener_actor_routine(json.dumps([1, 2]), DETECT_DROPLETS)

    parsed = json.loads(captured[0][1])
    assert parsed["detected_channels"] == []
    assert parsed["success"] is True


def test_error_mode_returns_success_false(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DETECT_DROPLETS

    captured = []
    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: captured.append((topic, message)),
    )

    r = DropletDetectionResponder(mode="error")
    r.listener_actor_routine(json.dumps([1, 2]), DETECT_DROPLETS)

    parsed = json.loads(captured[0][1])
    assert parsed["success"] is False
    assert parsed["error"] != ""


def test_last_request_channels_is_recorded(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DETECT_DROPLETS

    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: None,
    )

    r = DropletDetectionResponder(mode="succeed")
    r.listener_actor_routine(json.dumps([7, 8, 9]), DETECT_DROPLETS)
    assert list(r.last_request_channels) == [7, 8, 9]

"""Tests for the in-process camera demo responder.

Doesn't require Redis — exercises the actor function directly.
"""
import json
from unittest.mock import MagicMock, call, patch

from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_ACTIVE,
    DEVICE_VIEWER_MEDIA_CAPTURED,
    DEVICE_VIEWER_SCREEN_CAPTURE,
    DEVICE_VIEWER_SCREEN_RECORDING,
)
from video_protocol_controls.demos.camera_responder import (
    DEMO_CAMERA_RESPONDER_ACTOR_NAME,
    _demo_camera_responder,
    subscribe_demo_responder,
)

_PATCH = "video_protocol_controls.demos.camera_responder.publish_message"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_actor_name_constant_is_stable():
    """Demo wiring relies on this name being stable across import cycles."""
    assert DEMO_CAMERA_RESPONDER_ACTOR_NAME == "ppt6_demo_camera_responder"


# ---------------------------------------------------------------------------
# CAMERA_ACTIVE — fire-and-forget, no media output
# ---------------------------------------------------------------------------

def test_camera_active_logs_but_does_not_publish():
    """Camera on/off state carries no media output — no ack should be sent."""
    with patch(_PATCH) as mock_publish:
        _demo_camera_responder("true", DEVICE_VIEWER_CAMERA_ACTIVE)

    mock_publish.assert_not_called()


# ---------------------------------------------------------------------------
# SCREEN_CAPTURE — publishes synthetic image media_captured
# ---------------------------------------------------------------------------

def test_screen_capture_publishes_image_media_captured():
    """A capture message should publish a MEDIA_CAPTURED ack with type 'image'."""
    published = []
    with patch(_PATCH, side_effect=lambda **kw: published.append(kw)):
        _demo_camera_responder(
            json.dumps({"step_id": "abc", "format": "png"}),
            DEVICE_VIEWER_SCREEN_CAPTURE,
        )

    assert len(published) == 1
    assert published[0]["topic"] == DEVICE_VIEWER_MEDIA_CAPTURED
    body = json.loads(published[0]["message"])
    assert body["type"] == "image"
    assert "abc" in body["path"]


def test_screen_capture_malformed_json_does_not_raise():
    """Bad JSON in a capture payload should be silently swallowed."""
    with patch(_PATCH) as mock_publish:
        _demo_camera_responder("not-json", DEVICE_VIEWER_SCREEN_CAPTURE)

    mock_publish.assert_not_called()


# ---------------------------------------------------------------------------
# SCREEN_RECORDING — start is silent; stop publishes synthetic video ack
# ---------------------------------------------------------------------------

def test_screen_recording_start_does_not_publish():
    """Only a record-stop produces a media file — start is silent."""
    with patch(_PATCH) as mock_publish:
        _demo_camera_responder(
            json.dumps({"action": "start"}),
            DEVICE_VIEWER_SCREEN_RECORDING,
        )

    mock_publish.assert_not_called()


def test_screen_recording_stop_publishes_video_media_captured():
    """A record-stop message should publish a MEDIA_CAPTURED ack with type 'video'."""
    published = []
    with patch(_PATCH, side_effect=lambda **kw: published.append(kw)):
        _demo_camera_responder(
            json.dumps({"action": "stop"}),
            DEVICE_VIEWER_SCREEN_RECORDING,
        )

    assert len(published) == 1
    assert published[0]["topic"] == DEVICE_VIEWER_MEDIA_CAPTURED
    body = json.loads(published[0]["message"])
    assert body["type"] == "video"


def test_screen_recording_malformed_json_does_not_raise():
    """Bad JSON in a recording payload should be silently swallowed."""
    with patch(_PATCH) as mock_publish:
        _demo_camera_responder("not-json", DEVICE_VIEWER_SCREEN_RECORDING)

    mock_publish.assert_not_called()


# ---------------------------------------------------------------------------
# subscribe_demo_responder — router wiring
# ---------------------------------------------------------------------------

def test_subscribe_demo_responder_registers_all_three_topics():
    """subscribe_demo_responder must wire all three camera request topics."""
    router = MagicMock()

    subscribe_demo_responder(router)

    expected_calls = [
        call(
            topic=DEVICE_VIEWER_CAMERA_ACTIVE,
            subscribing_actor_name=DEMO_CAMERA_RESPONDER_ACTOR_NAME,
        ),
        call(
            topic=DEVICE_VIEWER_SCREEN_CAPTURE,
            subscribing_actor_name=DEMO_CAMERA_RESPONDER_ACTOR_NAME,
        ),
        call(
            topic=DEVICE_VIEWER_SCREEN_RECORDING,
            subscribing_actor_name=DEMO_CAMERA_RESPONDER_ACTOR_NAME,
        ),
    ]
    router.message_router_data.add_subscriber_to_topic.assert_has_calls(
        expected_calls, any_order=False
    )
    assert router.message_router_data.add_subscriber_to_topic.call_count == 3

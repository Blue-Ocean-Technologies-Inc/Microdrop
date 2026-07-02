"""Tests for the in-process magnet demo responder.

Doesn't require Redis — exercises the actor function directly.
"""
import json
from unittest.mock import patch

from peripheral_controller.consts import (
    PROTOCOL_SET_MAGNET, MAGNET_APPLIED,
)
from peripheral_protocol_controls.demos.magnet_responder import (
    DEMO_MAGNET_RESPONDER_ACTOR_NAME, _demo_magnet_responder,
)


def test_engage_request_publishes_magnet_applied_one():
    published = []
    with patch(
        "peripheral_protocol_controls.demos.magnet_responder.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        _demo_magnet_responder(
            json.dumps({"on": True, "height_mm": 5.0}),
            PROTOCOL_SET_MAGNET,
        )

    assert published == [{"topic": MAGNET_APPLIED, "message": "1"}]


def test_retract_request_publishes_magnet_applied_zero():
    published = []
    with patch(
        "peripheral_protocol_controls.demos.magnet_responder.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        _demo_magnet_responder(
            json.dumps({"on": False, "height_mm": 0.0}),
            PROTOCOL_SET_MAGNET,
        )

    assert published == [{"topic": MAGNET_APPLIED, "message": "0"}]


def test_actor_name_constant_is_stable():
    """ProtocolSession demos rely on this name being stable for subscription."""
    assert DEMO_MAGNET_RESPONDER_ACTOR_NAME == "ppt_demo_magnet_responder"

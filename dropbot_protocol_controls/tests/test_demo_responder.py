# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the in-process voltage/frequency demo responder.

Doesn't require Redis -- exercises the actor function directly.
"""
from unittest.mock import patch

from dropbot_controller.consts import (
    PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    DEMO_VF_RESPONDER_ACTOR_NAME, _demo_voltage_frequency_responder,
)


def test_voltage_request_publishes_voltage_applied_ack():
    published = []
    with patch(
        "dropbot_protocol_controls.demos.voltage_frequency_responder.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        _demo_voltage_frequency_responder("100", PROTOCOL_SET_VOLTAGE)

    assert published == [{"topic": VOLTAGE_APPLIED, "message": "100"}]


def test_frequency_request_publishes_frequency_applied_ack():
    published = []
    with patch(
        "dropbot_protocol_controls.demos.voltage_frequency_responder.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        _demo_voltage_frequency_responder("10000", PROTOCOL_SET_FREQUENCY)

    assert published == [{"topic": FREQUENCY_APPLIED, "message": "10000"}]


def test_unknown_topic_does_not_publish():
    """Defensive: receiving an unrecognized topic should not ack anything."""
    published = []
    with patch(
        "dropbot_protocol_controls.demos.voltage_frequency_responder.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        _demo_voltage_frequency_responder("xyz", "dropbot/requests/some_other")

    assert published == []


def test_actor_name_constant_is_stable():
    """ProtocolSession demos rely on this name being stable for subscription."""
    assert DEMO_VF_RESPONDER_ACTOR_NAME == "ppt_demo_voltage_frequency_responder"

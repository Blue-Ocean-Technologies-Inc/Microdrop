# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for ProtocolTreeDisplayMessage Pydantic model + topic constant."""

from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)


def test_topic_constant_value():
    assert PROTOCOL_TREE_DISPLAY_STATE == "ui/protocol_tree_display_state"


def test_topic_last_segment_unique_vs_protocol_grid():
    """Regression: dramatiq listener dispatches by topic.split('/')[-1].
    If two topics share a last segment, the second one's handler is
    silently shadowed. PROTOCOL_GRID_DISPLAY_STATE ends in
    'display_state'; PROTOCOL_TREE_DISPLAY_STATE must NOT."""
    from device_viewer.consts import PROTOCOL_GRID_DISPLAY_STATE
    grid_last = PROTOCOL_GRID_DISPLAY_STATE.split("/")[-1]
    tree_last = PROTOCOL_TREE_DISPLAY_STATE.split("/")[-1]
    assert grid_last != tree_last


def test_default_construction_is_free_mode_empty():
    msg = ProtocolTreeDisplayMessage()
    assert msg.electrodes == []
    assert msg.routes == []
    assert msg.step_id is None
    assert msg.step_label is None
    assert msg.free_mode is False
    assert msg.editable is True


def test_step_payload_round_trip():
    msg = ProtocolTreeDisplayMessage(
        electrodes=["e00", "e01"],
        routes=[["e02", "e03", "e04"]],
        step_id="abc123",
        step_label="Wash",
        free_mode=False,
        editable=True,
    )
    rt = ProtocolTreeDisplayMessage.deserialize(msg.serialize())
    assert rt.electrodes == ["e00", "e01"]
    assert rt.routes == [["e02", "e03", "e04"]]
    assert rt.step_id == "abc123"
    assert rt.step_label == "Wash"
    assert rt.free_mode is False
    assert rt.editable is True


def test_free_mode_payload_round_trip():
    msg = ProtocolTreeDisplayMessage(free_mode=True)
    rt = ProtocolTreeDisplayMessage.deserialize(msg.serialize())
    assert rt.free_mode is True
    assert rt.electrodes == []
    assert rt.routes == []
    assert rt.step_id is None
    assert rt.step_label is None

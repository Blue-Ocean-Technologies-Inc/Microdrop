# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Round-trip tests for the tree's generic sync message models."""

from pluggable_protocol_tree.models.cell_sync import (
    ProtocolTreeAddStepMessage,
    ProtocolTreeRowSelectedMessage,
)


def test_add_step_message_round_trip():
    msg = ProtocolTreeAddStepMessage(
        after_step_id="abc123", cells={"fluorescence_chain": [{"label": "GFP"}]},
        name="Step (capture chain)")
    back = ProtocolTreeAddStepMessage.deserialize(msg.serialize())
    assert back.after_step_id == "abc123"
    assert back.group_id is None
    assert back.cells == {"fluorescence_chain": [{"label": "GFP"}]}
    assert back.name == "Step (capture chain)"


def test_add_step_message_defaults():
    msg = ProtocolTreeAddStepMessage.deserialize(
        ProtocolTreeAddStepMessage(cells={}).serialize())
    assert msg.after_step_id is None and msg.group_id is None
    assert msg.cells == {} and msg.name is None


def test_row_selected_message_gains_group_id():
    msg = ProtocolTreeRowSelectedMessage(step_id=None, group_id="grp1", cells={})
    back = ProtocolTreeRowSelectedMessage.deserialize(msg.serialize())
    assert back.group_id == "grp1" and back.step_id is None


def test_row_selected_message_back_compat_without_group_id():
    # Payloads serialized by older senders must still parse.
    back = ProtocolTreeRowSelectedMessage.deserialize(
        '{"step_id": "s1", "cells": {}}')
    assert back.step_id == "s1" and back.group_id is None

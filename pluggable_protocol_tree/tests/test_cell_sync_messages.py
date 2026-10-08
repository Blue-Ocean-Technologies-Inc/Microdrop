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

# Standard library imports.
import json

# Microdrop package imports.
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.cell_sync import (
    ProtocolTreeAddStepMessage,
    ProtocolTreeRowSelectedMessage,
    ProtocolTreeRowSelectedPublisher,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import (
    _selected_step_uuids,
)

# Microdrop utils imports.
import microdrop_utils.dramatiq_pub_sub_helpers as pub_sub


def test_add_step_message_round_trip():
    msg = ProtocolTreeAddStepMessage(
        after_step_id="abc123",
        cells={"fluorescence_chain": [{"label": "GFP"}]},
        name="Step (capture chain)",
    )
    back = ProtocolTreeAddStepMessage.deserialize(msg.serialize())
    assert back.after_step_id == "abc123"
    assert back.group_id is None
    assert back.cells == {"fluorescence_chain": [{"label": "GFP"}]}
    assert back.name == "Step (capture chain)"


def test_add_step_message_defaults():
    msg = ProtocolTreeAddStepMessage.deserialize(
        ProtocolTreeAddStepMessage(cells={}).serialize()
    )
    assert msg.after_step_id is None and msg.group_id is None
    assert msg.cells == {} and msg.name is None


def test_row_selected_message_gains_group_id():
    msg = ProtocolTreeRowSelectedMessage(step_id=None, group_id="grp1", cells={})
    back = ProtocolTreeRowSelectedMessage.deserialize(msg.serialize())
    assert back.group_id == "grp1" and back.step_id is None


def test_row_selected_message_back_compat_without_group_id():
    # Payloads serialized by older senders must still parse.
    back = ProtocolTreeRowSelectedMessage.deserialize('{"step_id": "s1", "cells": {}}')
    assert back.step_id == "s1" and back.group_id is None


# --- selected_step_ids (multi-selection) ---


def test_row_selected_message_selected_step_ids_defaults_empty():
    back = ProtocolTreeRowSelectedMessage.deserialize(
        ProtocolTreeRowSelectedMessage(step_id="s1").serialize()
    )

    assert back.selected_step_ids == []


def test_row_selected_message_selected_step_ids_round_trip():
    msg = ProtocolTreeRowSelectedMessage(
        step_id="s2", cells={}, selected_step_ids=["s1", "s2", "s3"]
    )

    back = ProtocolTreeRowSelectedMessage.deserialize(msg.serialize())

    assert back.selected_step_ids == ["s1", "s2", "s3"]


def test_row_selected_message_back_compat_without_selected_step_ids():
    back = ProtocolTreeRowSelectedMessage.deserialize(
        '{"step_id": "s1", "group_id": null, "cells": {}}'
    )

    assert back.selected_step_ids == []


def _publish_recorder(monkeypatch):
    sent = []
    monkeypatch.setattr(
        pub_sub, "publish_message", lambda **kw: sent.append(json.loads(kw["message"]))
    )

    return sent


def test_row_selected_publisher_carries_selected_step_ids(monkeypatch):
    sent = _publish_recorder(monkeypatch)
    publisher = ProtocolTreeRowSelectedPublisher(topic="t")

    publisher.publish(step_id="s2", cells={}, selected_step_ids=("s1", "s2"))

    assert sent[0]["selected_step_ids"] == ["s1", "s2"]


def test_row_selected_publisher_selected_step_ids_default(monkeypatch):
    sent = _publish_recorder(monkeypatch)
    publisher = ProtocolTreeRowSelectedPublisher(topic="t")

    publisher.publish(step_id="s1", cells={})

    assert sent[0]["selected_step_ids"] == []


def _manager_with_group():
    """Steps A, B, a group holding C, then D (root paths 0..3)."""
    manager = RowManager(columns=[make_type_column(), make_name_column()])
    manager.add_step(values={"name": "A"})
    manager.add_step(values={"name": "B"})
    manager.add_group()
    manager.add_step(parent_path=(2,), values={"name": "C"})
    manager.add_step(values={"name": "D"})

    return manager


def test_selected_step_uuids_follow_selection_in_tree_order():
    manager = _manager_with_group()
    a, b, group, d = manager.root.children
    c = group.children[0]

    # Click order D, C, A: the broadcast lists them in tree order.
    manager.select([(3,), (2, 0), (0,)], mode="set")

    assert _selected_step_uuids(manager) == [a.uuid, c.uuid, d.uuid]

    manager.select([(1,)], mode="set")

    assert _selected_step_uuids(manager) == [b.uuid]


def test_selected_step_uuids_exclude_groups_and_stale_paths():
    manager = _manager_with_group()
    a = manager.root.children[0]

    manager.select([(0,), (2,), (9,)], mode="set")

    assert _selected_step_uuids(manager) == [a.uuid]


def test_selected_step_uuids_empty_without_selection():
    assert _selected_step_uuids(_manager_with_group()) == []

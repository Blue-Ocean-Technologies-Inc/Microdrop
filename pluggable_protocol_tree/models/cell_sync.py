# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pydantic contracts for the tree's generic per-cell sync topics.

``PROTOCOL_TREE_ROW_SELECTED`` — broadcast by the tree's sync controller
on every selection change, and again on any cell edit of the selected
step: the selected step's uuid plus EVERY column's serialized value.
Column-owning plugins (fluorescence, magnet, ...) live-track the selected
step through this without reaching into the tree. ``step_id`` None = no
step selected (free mode / group row). ``step_id`` is the tree's CURRENT
row (the one the device viewer shows and cell-edit rebroadcasts key on);
``selected_step_ids`` lists every selected step row's uuid in tree order
(groups excluded) — it need not contain ``step_id`` (Ctrl-click can
deselect the current row) and is empty from senders predating it.

``PROTOCOL_TREE_SET_CELL`` — request handled by the sync controller:
write ``value`` (the column's serialized form) into one step's cell,
equality-skipped and fired through ``cell_changed`` like a manual edit.
``only_if_set`` restricts the write to cells that currently hold a value,
so a pane edit never populates an unchecked step. Ignored while a
protocol runs — the executor owns the rows then.

``PROTOCOL_TREE_ADD_STEP`` — request handled by the sync controller:
insert a new step carrying ``cells`` (columns' serialized forms) either
immediately after the step ``after_step_id``, or as the last child of
the group ``group_id``, or appended at the root when neither is given.
Ignored while a protocol runs — the executor owns the rows then.
"""

# Standard library imports.
from typing import Any

# Third-party imports.
from pydantic import BaseModel

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher


class ProtocolTreeRowSelectedMessage(BaseModel):
    step_id: str | None = None
    group_id: str | None = None
    cells: dict[str, Any] = {}
    selected_step_ids: list[str] = []

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "ProtocolTreeRowSelectedMessage":
        return cls.model_validate_json(json_str)


class ProtocolTreeSetCellMessage(BaseModel):
    step_id: str
    col_id: str
    value: Any = None
    only_if_set: bool = False

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "ProtocolTreeSetCellMessage":
        return cls.model_validate_json(json_str)


class ProtocolTreeRowSelectedPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``PROTOCOL_TREE_ROW_SELECTED``."""

    validator_class = ProtocolTreeRowSelectedMessage

    def publish(self, *, step_id, cells, group_id=None, selected_step_ids=None, **kw):
        super().publish(
            {
                "step_id": step_id,
                "group_id": group_id,
                "cells": cells,
                "selected_step_ids": list(selected_step_ids or []),
            },
            **kw,
        )


class ProtocolTreeSetCellPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``PROTOCOL_TREE_SET_CELL``."""

    validator_class = ProtocolTreeSetCellMessage

    def publish(self, *, step_id, col_id, value, only_if_set=False, **kw):
        super().publish(
            {
                "step_id": step_id,
                "col_id": col_id,
                "value": value,
                "only_if_set": only_if_set,
            },
            **kw,
        )


class ProtocolTreeAddStepMessage(BaseModel):
    after_step_id: str | None = None
    group_id: str | None = None
    cells: dict[str, Any] = {}
    name: str | None = None

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "ProtocolTreeAddStepMessage":
        return cls.model_validate_json(json_str)


class ProtocolTreeAddStepPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``PROTOCOL_TREE_ADD_STEP``."""

    validator_class = ProtocolTreeAddStepMessage

    def publish(self, *, after_step_id=None, group_id=None, cells, name=None, **kw):
        super().publish(
            {
                "after_step_id": after_step_id,
                "group_id": group_id,
                "cells": cells,
                "name": name,
            },
            **kw,
        )

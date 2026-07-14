"""Pydantic contracts for the tree's generic per-cell sync topics.

``PROTOCOL_TREE_ROW_SELECTED`` — broadcast by the tree's sync controller
on every selection change, and again on any cell edit of the selected
step: the selected step's uuid plus EVERY column's serialized value.
Column-owning plugins (fluorescence, magnet, ...) live-track the selected
step through this without reaching into the tree. ``step_id`` None = no
step selected (free mode / group row).

``PROTOCOL_TREE_SET_CELL`` — request handled by the sync controller:
write ``value`` (the column's serialized form) into one step's cell,
equality-skipped and fired through ``cell_changed`` like a manual edit.
``only_if_set`` restricts the write to cells that currently hold a value,
so a pane edit never populates an unchecked step. Ignored while a
protocol runs — the executor owns the rows then.
"""

from typing import Any

from pydantic import BaseModel

from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher


class ProtocolTreeRowSelectedMessage(BaseModel):
    step_id: str | None = None
    cells: dict[str, Any] = {}

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

    def publish(self, *, step_id, cells, **kw):
        super().publish({"step_id": step_id, "cells": cells}, **kw)


class ProtocolTreeSetCellPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``PROTOCOL_TREE_SET_CELL``."""
    validator_class = ProtocolTreeSetCellMessage

    def publish(self, *, step_id, col_id, value, only_if_set=False, **kw):
        super().publish({
            "step_id": step_id,
            "col_id": col_id,
            "value": value,
            "only_if_set": only_if_set,
        }, **kw)

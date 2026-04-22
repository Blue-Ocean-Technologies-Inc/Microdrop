"""End-to-end smoke test.

Headless test that exercises the full stack: create a manager, add
groups and steps via the manager, verify the QAbstractItemModel
reflects them, save to JSON, load back, confirm identical tree shape.
Does not require pytest-qt — a QCoreApplication is sufficient for the
tree model's structural queries."""

import json

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column


def _cols():
    return [make_type_column(), make_id_column(), make_name_column(),
            make_duration_column()]


def test_full_round_trip():
    m = RowManager(columns=_cols())
    g = m.add_group(name="Wash")
    m.add_step(parent_path=g, values={"name": "Drop", "duration_s": 2.0})
    m.add_step(parent_path=g, values={"name": "Off", "duration_s": 1.5})
    m.add_step(values={"name": "Settle", "duration_s": 5.0})

    qm = MvcTreeModel(m)
    assert qm.rowCount() == 2   # top-level: Wash + Settle

    data = m.to_json()
    serialized = json.dumps(data)

    data_back = json.loads(serialized)
    m2 = RowManager.from_json(data_back, columns=_cols())
    qm2 = MvcTreeModel(m2)
    assert qm2.rowCount() == 2

    wash = m2.root.children[0]
    assert wash.name == "Wash"
    assert [c.name for c in wash.children] == ["Drop", "Off"]
    assert [c.duration_s for c in wash.children] == [2.0, 1.5]
    assert m2.root.children[1].name == "Settle"

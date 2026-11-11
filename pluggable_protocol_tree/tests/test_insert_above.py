# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the tree widget's "Insert Step/Group Above" context actions.

Both insert a sibling immediately before the anchored row, whether that row
is a step or a group, and select the new row.
"""

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


@pytest.fixture
def manager():
    """Root: [A, Wash{B, C}, Empty]."""
    rm = RowManager(
        columns=[
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
        ]
    )
    rm.add_step(values={"name": "A"})
    g = rm.add_group(name="Wash")
    rm.add_step(parent_path=g, values={"name": "B"})
    rm.add_step(parent_path=g, values={"name": "C"})
    rm.add_group(name="Empty")
    return rm


@pytest.fixture
def widget(qapp, manager):
    return ProtocolTreeWidget(manager)


def _index_for(widget, manager, path):
    return widget._node_to_index(manager.get_row(path))


def _names(manager, parent_path=()):
    parent = manager.get_row(parent_path) if parent_path else manager.root
    return [child.name for child in parent.children]


def test_insert_step_above_root_step_shifts_it_down(widget, manager):
    widget._insert_step_above(_index_for(widget, manager, (0,)))

    names = _names(manager)
    assert len(names) == 4
    assert names[1:] == ["A", "Wash", "Empty"]
    assert not isinstance(manager.get_row((0,)), GroupRow)


def test_insert_group_above_nested_step_stays_in_parent(widget, manager):
    widget._insert_group_above(_index_for(widget, manager, (1, 1)))

    assert _names(manager) == ["A", "Wash", "Empty"]

    nested = manager.get_row((1,)).children
    assert [nested[0].name, nested[2].name] == ["B", "C"]
    assert isinstance(nested[1], GroupRow)


def test_insert_step_above_group_is_a_sibling_not_a_child(widget, manager):
    widget._insert_step_above(_index_for(widget, manager, (1,)))

    names = _names(manager)
    assert names[0] == "A"
    assert names[2:] == ["Wash", "Empty"]
    assert not isinstance(manager.get_row((1,)), GroupRow)
    assert _names(manager, (2,)) == ["B", "C"]


def test_inserted_row_becomes_the_selection(widget, manager):
    manager.select([(2,)])

    widget._insert_step_above(_index_for(widget, manager, (1, 0)))

    assert manager.selection == [(1, 0)]

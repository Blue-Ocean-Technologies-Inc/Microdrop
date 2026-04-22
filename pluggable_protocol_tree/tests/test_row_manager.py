"""Tests for RowManager structure, selection, clipboard, iteration, slicing."""

import pytest

from pluggable_protocol_tree.models.row import BaseRow, GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column


@pytest.fixture
def columns():
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_duration_column(),
    ]


@pytest.fixture
def manager(columns):
    return RowManager(columns=columns)


# --- construction ---

def test_row_manager_has_empty_root_on_construction(manager):
    assert manager.root is not None
    assert isinstance(manager.root, GroupRow)
    assert manager.root.children == []


def test_row_manager_builds_step_and_group_subclasses(manager):
    assert manager.step_type is not None
    assert manager.group_type is not None
    # Dynamic subclasses should carry the duration trait from the column
    step = manager.step_type()
    assert step.duration_s == 1.0


# --- add_step / add_group ---

def test_add_step_at_root(manager):
    path = manager.add_step()
    assert path == (0,)
    assert len(manager.root.children) == 1


def test_add_group_at_root(manager):
    path = manager.add_group(name="Wash")
    assert path == (0,)
    assert manager.root.children[0].name == "Wash"


def test_add_step_inside_group(manager):
    gpath = manager.add_group(name="Wash")
    spath = manager.add_step(parent_path=gpath)
    assert spath == (0, 0)
    g = manager.root.children[0]
    assert len(g.children) == 1


def test_add_step_with_values(manager):
    path = manager.add_step(values={"duration_s": 3.5, "name": "DropOn"})
    row = manager.get_row(path)
    assert row.duration_s == 3.5
    assert row.name == "DropOn"


# --- remove ---

def test_remove_single_row(manager):
    manager.add_step()
    p = manager.add_step()
    manager.remove([p])
    assert len(manager.root.children) == 1


def test_remove_group_removes_children(manager):
    gpath = manager.add_group()
    manager.add_step(parent_path=gpath)
    manager.add_step(parent_path=gpath)
    manager.remove([gpath])
    assert manager.root.children == []


# --- move ---

def test_move_reorders_within_parent(manager):
    a = manager.add_step(values={"name": "A"})
    b = manager.add_step(values={"name": "B"})
    manager.move([a], target_parent_path=(), target_index=2)   # move A after B
    names = [r.name for r in manager.root.children]
    assert names == ["B", "A"]


def test_move_reparents_into_group(manager):
    g = manager.add_group()
    s = manager.add_step(values={"name": "S"})
    manager.move([s], target_parent_path=g, target_index=0)
    new_group = manager.root.children[0]
    assert len(new_group.children) == 1
    assert new_group.children[0].name == "S"

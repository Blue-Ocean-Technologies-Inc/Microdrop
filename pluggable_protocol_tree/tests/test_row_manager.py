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


# --- selection ---

def test_select_set_replaces_selection(manager):
    a = manager.add_step()
    b = manager.add_step()
    manager.select([a])
    manager.select([b], mode="set")
    assert manager.selection == [b]


def test_select_add_appends(manager):
    a = manager.add_step()
    b = manager.add_step()
    manager.select([a])
    manager.select([b], mode="add")
    assert manager.selection == [a, b]


def test_select_range_fills_between(manager):
    paths = [manager.add_step() for _ in range(5)]
    manager.select([paths[1], paths[3]], mode="range")
    # Range selects all top-level siblings between the two
    assert manager.selection == [paths[1], paths[2], paths[3]]


def test_selected_rows_returns_row_objects(manager):
    a = manager.add_step(values={"name": "A"})
    b = manager.add_step(values={"name": "B"})
    manager.select([a, b])
    names = [r.name for r in manager.selected_rows()]
    assert names == ["A", "B"]


# --- uuid lookup ---

def test_get_row_by_uuid_returns_row(manager):
    p = manager.add_step()
    row = manager.get_row(p)
    assert manager.get_row_by_uuid(row.uuid) is row


def test_get_row_by_uuid_none_for_unknown(manager):
    assert manager.get_row_by_uuid("does-not-exist") is None


def test_get_row_by_uuid_searches_nested(manager):
    g = manager.add_group()
    s = manager.add_step(parent_path=g)
    row = manager.get_row(s)
    assert manager.get_row_by_uuid(row.uuid) is row


# --- clipboard ---

def test_copy_paste_round_trip_preserves_names(manager):
    a = manager.add_step(values={"name": "A", "duration_s": 2.0})
    manager.select([a])
    # Use an in-memory clipboard surrogate so tests don't depend on a
    # running QApplication — RowManager exposes a serialize_selection
    # helper that returns the payload, and paste_from_json accepts it.
    payload = manager._serialize_selection()
    assert payload["rows"][0][manager._field_index("name")] == "A"

    manager._paste_from_payload(payload, target_path=None)
    assert len(manager.root.children) == 2
    assert manager.root.children[1].name == "A"


def test_copy_paste_regenerates_uuids(manager):
    a = manager.add_step()
    original_uuid = manager.get_row(a).uuid
    manager.select([a])
    payload = manager._serialize_selection()
    manager._paste_from_payload(payload, target_path=None)
    pasted = manager.root.children[1]
    assert pasted.uuid != original_uuid


def test_cut_removes_originals(manager):
    a = manager.add_step(values={"name": "A"})
    b = manager.add_step(values={"name": "B"})
    manager.select([a])
    payload = manager._serialize_selection()
    manager.remove([a])   # cut = copy + remove; here we drive manually
    assert [r.name for r in manager.root.children] == ["B"]
    manager._paste_from_payload(payload, target_path=None)
    assert [r.name for r in manager.root.children] == ["B", "A"]


def test_copy_paste_includes_children_of_groups(manager):
    g = manager.add_group(name="G")
    manager.add_step(parent_path=g, values={"name": "Inner"})
    manager.select([g])
    payload = manager._serialize_selection()
    manager._paste_from_payload(payload, target_path=None)
    copied_group = manager.root.children[1]
    assert copied_group.name == "G"
    assert len(copied_group.children) == 1
    assert copied_group.children[0].name == "Inner"


# --- iter_execution_steps ---

def test_iter_execution_flat_protocol(manager):
    manager.add_step(values={"name": "A"})
    manager.add_step(values={"name": "B"})
    names = [r.name for r in manager.iter_execution_steps()]
    assert names == ["A", "B"]


def test_iter_execution_flattens_groups(manager):
    g = manager.add_group(name="G")
    manager.add_step(parent_path=g, values={"name": "A"})
    manager.add_step(parent_path=g, values={"name": "B"})
    manager.add_step(values={"name": "C"})
    names = [r.name for r in manager.iter_execution_steps()]
    assert names == ["A", "B", "C"]


def test_iter_execution_expands_repetitions(manager):
    """Until PPT-1 integrates the repetitions column, the default
    repetitions value is 1. The iter_execution_steps loop reads a
    `repetitions` attribute if present, defaulting to 1."""
    manager.add_step(values={"name": "A"})
    s = manager.add_step(values={"name": "B"})
    # Simulate the repetitions column by assigning the attribute dynamically
    # (real repetitions column lands alongside this method — see comment in
    # RowManager.iter_execution_steps for the contract).
    setattr(manager.get_row(s), "repetitions", 3)
    names = [r.name for r in manager.iter_execution_steps()]
    # A once, B three times (in order)
    assert names == ["A", "B", "B", "B"]


def test_iter_execution_group_repetitions_expand(manager):
    g = manager.add_group(name="G")
    manager.add_step(parent_path=g, values={"name": "A"})
    manager.add_step(parent_path=g, values={"name": "B"})
    setattr(manager.get_row(g), "repetitions", 2)
    names = [r.name for r in manager.iter_execution_steps()]
    assert names == ["A", "B", "A", "B"]

"""Tests for BaseRow and GroupRow structure."""

from pluggable_protocol_tree.models.row import BaseRow, GroupRow


def test_base_row_auto_generates_uuid():
    r = BaseRow()
    assert r.uuid
    assert len(r.uuid) == 32   # hex uuid4


def test_base_row_two_instances_have_different_uuids():
    assert BaseRow().uuid != BaseRow().uuid


def test_base_row_default_type_is_step():
    assert BaseRow().row_type == "step"


def test_group_row_default_type_is_group():
    assert GroupRow().row_type == "group"


def test_group_add_row_sets_parent_and_appends():
    g = GroupRow(name="Group")
    r = BaseRow(name="Step")
    g.add_row(r)
    assert r.parent is g
    assert g.children == [r]


def test_group_insert_row_at_position():
    g = GroupRow(name="Group")
    a, b, c = BaseRow(name="A"), BaseRow(name="B"), BaseRow(name="C")
    g.add_row(a)
    g.add_row(c)
    g.insert_row(1, b)
    assert [r.name for r in g.children] == ["A", "B", "C"]


def test_group_remove_row_clears_parent():
    g = GroupRow(name="Group")
    r = BaseRow(name="Step")
    g.add_row(r)
    g.remove_row(r)
    assert r.parent is None
    assert g.children == []


def test_path_top_level_row_has_empty_path():
    """A row with no parent has an empty path tuple.

    Only rows *under* a parent have positional paths; the root group
    itself is invisible and doesn't count as a parent in path derivation.
    """
    r = BaseRow()
    assert r.path == ()


def test_path_nested_row_has_0_indexed_tuple():
    root = GroupRow(name="Root")
    a = BaseRow(name="A")
    b = BaseRow(name="B")
    root.add_row(a)
    root.add_row(b)
    # a is at position 0 under root, b at position 1
    assert a.path == (0,)
    assert b.path == (1,)


def test_path_doubly_nested():
    root = GroupRow(name="Root")
    g = GroupRow(name="Group")
    s = BaseRow(name="Step")
    root.add_row(g)
    g.add_row(s)
    assert g.path == (0,)
    assert s.path == (0, 0)

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


def test_path_updates_when_sibling_inserted_before():
    root = GroupRow(name="Root")
    a = BaseRow(name="A")
    root.add_row(a)
    assert a.path == (0,)
    root.insert_row(0, BaseRow(name="B"))
    assert a.path == (1,)


def test_path_updates_after_remove():
    root = GroupRow(name="Root")
    a, b = BaseRow(name="A"), BaseRow(name="B")
    root.add_row(a)
    root.add_row(b)
    assert b.path == (1,)
    root.remove_row(a)
    assert b.path == (0,)


def test_path_updates_when_ancestor_sibling_inserted():
    """A change at the root level must propagate to deeply nested paths."""
    root = GroupRow(name="Root")
    g = GroupRow(name="Group")
    s = BaseRow(name="Step")
    root.add_row(g)
    g.add_row(s)
    assert s.path == (0, 0)
    root.insert_row(0, GroupRow(name="Other"))
    assert s.path == (1, 0)


# --- build_row_type tests ---

from unittest.mock import MagicMock
from traits.api import Float, Int

from pluggable_protocol_tree.models.row import build_row_type, BaseRow, GroupRow


def _mock_column(col_id, trait):
    """Minimal column stand-in for build_row_type tests.

    Only the model.col_id and model.trait_for_row() surface are exercised
    here; real IColumn is introduced in Task 6.
    """
    c = MagicMock()
    c.model.col_id = col_id
    c.model.trait_for_row.return_value = trait
    return c


def test_build_row_type_adds_declared_traits():
    cols = [_mock_column("voltage", Float(100.0)),
            _mock_column("reps", Int(1))]
    RowType = build_row_type(cols, base=BaseRow)
    r = RowType()
    # Declared traits are present with their defaults
    assert r.voltage == 100.0
    assert r.reps == 1


def test_build_row_type_preserves_base_traits():
    cols = [_mock_column("voltage", Float(50.0))]
    RowType = build_row_type(cols, base=BaseRow)
    r = RowType(name="Custom")
    assert r.name == "Custom"
    assert r.row_type == "step"
    assert r.uuid  # still auto-generated


def test_build_row_type_for_group_base():
    cols = [_mock_column("voltage", Float(0.0))]
    GroupType = build_row_type(cols, base=GroupRow, name="ProtocolGroupRow")
    g = GroupType(name="G")
    assert g.row_type == "group"
    assert g.voltage == 0.0
    # children list still works
    child = GroupType(name="Child")
    g.add_row(child)
    assert g.children == [child]


def test_build_row_type_distinct_classes_do_not_share_traits():
    """Fresh type() calls must not leak traits across invocations."""
    TypeA = build_row_type([_mock_column("a", Float(1.0))], base=BaseRow, name="A")
    TypeB = build_row_type([_mock_column("b", Float(2.0))], base=BaseRow, name="B")
    a = TypeA()
    b = TypeB()
    assert hasattr(a, "a") and not hasattr(a, "b")
    assert hasattr(b, "b") and not hasattr(b, "a")


def test_build_row_type_preserves_traits_semantics():
    """type() construction must route through MetaHasTraits: validation
    and observers must fire on dynamic-class instances. The whole design
    rests on this; a regression here would be silent and dangerous."""
    import pytest
    from traits.api import TraitError

    RowType = build_row_type([_mock_column("voltage", Float(0.0))], base=BaseRow)
    r = RowType()

    with pytest.raises(TraitError):
        r.voltage = "not a float"

    seen = []
    r.observe(lambda e: seen.append((e.old, e.new)), "voltage")
    r.voltage = 5.0
    assert seen == [(0.0, 5.0)]

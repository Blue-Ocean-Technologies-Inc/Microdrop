"""Tests for built-in columns shipped by the core plugin."""

from traits.api import Float, Str

from pluggable_protocol_tree.models.row import BaseRow, GroupRow, build_row_type
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column


# --- type column ---

def test_type_column_has_expected_metadata():
    col = make_type_column()
    assert col.model.col_id == "type"
    assert col.model.col_name == "Type"


def test_type_column_displays_row_type():
    col = make_type_column()
    assert col.view.format_display(None, BaseRow()) == "step"
    assert col.view.format_display(None, GroupRow()) == "group"


def test_type_column_is_read_only():
    from pyface.qt.QtCore import Qt
    col = make_type_column()
    assert not (col.view.get_flags(BaseRow()) & Qt.ItemIsEditable)


# --- name column ---

def test_name_column_renders_name_trait():
    col = make_name_column()
    r = BaseRow(name="Hello")
    assert col.model.get_value(r) == "Hello"


def test_name_column_is_editable():
    from pyface.qt.QtCore import Qt
    col = make_name_column()
    assert col.view.get_flags(BaseRow()) & Qt.ItemIsEditable


# --- duration column ---

def test_duration_column_default_one_second():
    col = make_duration_column()
    assert col.model.default_value == 1.0


def test_duration_column_trait_is_float():
    col = make_duration_column()
    trait = col.model.trait_for_row()
    # Building a row-type and instantiating should yield float default
    RowType = build_row_type([col], base=BaseRow)
    assert RowType().duration_s == 1.0


def test_duration_column_renders_on_group_but_not_editable_there():
    """Duration is not meaningful on groups (Q5 A + X: groups just
    organize)."""
    from pyface.qt.QtCore import Qt
    col = make_duration_column()
    # renders_on_group is True (so cell is shown) but the double-spinbox
    # view makes it non-editable on groups.
    flags = col.view.get_flags(GroupRow())
    assert not (flags & Qt.ItemIsEditable)


def test_duration_column_hidden_by_default_false():
    col = make_duration_column()
    assert col.view.hidden_by_default is False


# --- id column ---

from pluggable_protocol_tree.builtins.id_column import make_id_column


def test_id_column_read_only():
    from pyface.qt.QtCore import Qt
    col = make_id_column()
    assert not (col.view.get_flags(BaseRow()) & Qt.ItemIsEditable)


def test_id_column_top_level_display():
    """A top-level row at position 0 displays '1' (1-indexed)."""
    col = make_id_column()
    root = GroupRow(name="Root")
    a = BaseRow()
    b = BaseRow()
    root.add_row(a)
    root.add_row(b)
    assert col.view.format_display(None, a) == "1"
    assert col.view.format_display(None, b) == "2"


def test_id_column_nested_display():
    """Step 0 inside Group 0 inside Root displays '1.1'."""
    col = make_id_column()
    root = GroupRow(name="Root")
    g = GroupRow(name="G")
    s = BaseRow()
    root.add_row(g)
    g.add_row(s)
    assert col.view.format_display(None, g) == "1"
    assert col.view.format_display(None, s) == "1.1"


def test_id_column_orphan_row_empty():
    col = make_id_column()
    assert col.view.format_display(None, BaseRow()) == ""


# --- repetitions column ---

from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)


def test_repetitions_column_default_one():
    col = make_repetitions_column()
    assert col.model.default_value == 1


def test_repetitions_column_trait_is_int_with_default_one():
    col = make_repetitions_column()
    RowType = build_row_type([col], base=BaseRow)
    r = RowType()
    assert r.repetitions == 1


def test_repetitions_column_view_uses_intspinbox_range():
    col = make_repetitions_column()
    assert col.view.low == 1
    assert col.view.high == 1000


def test_repetitions_column_drives_iter_execution_steps_expansion():
    """Locks in the PPT-1 contract through a real column (not setattr)."""
    from pluggable_protocol_tree.models.row_manager import RowManager
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_repetitions_column(), make_duration_column()]
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "A", "repetitions": 3})
    names = [r.name for r in rm.iter_execution_steps()]
    assert names == ["A", "A", "A"]


def test_repetitions_column_metadata():
    col = make_repetitions_column()
    assert col.model.col_id == "repetitions"
    assert col.model.col_name == "Reps"


def test_repetitions_column_editable_on_groups():
    """Reps must be editable on group rows — that's the whole point of
    group repetitions. The base IntSpinBoxColumnView strips
    ItemIsEditable on groups; the reps column overrides that."""
    from pyface.qt.QtCore import Qt
    col = make_repetitions_column()
    flags = col.view.get_flags(GroupRow())
    assert flags & Qt.ItemIsEditable


# --- route_repetitions column (route-reps split) ---

def test_route_repetitions_column_metadata():
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    col = make_route_repetitions_column()
    assert col.model.col_id == "route_repetitions"
    assert col.model.col_name == "Route Reps"
    assert col.model.default_value == 1
    assert col.view.hidden_by_default is False
    assert col.view.low == 1 and col.view.high == 1000


def test_route_repetitions_editable_on_step_not_group():
    from pyface.qt.QtCore import Qt
    from pluggable_protocol_tree.models.row import BaseRow, GroupRow
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    col = make_route_repetitions_column()
    assert col.view.get_flags(BaseRow()) & Qt.ItemIsEditable
    assert not (col.view.get_flags(GroupRow()) & Qt.ItemIsEditable)


def test_route_reps_handler_plain_write_when_not_in_duration_mode():
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    col = make_route_repetitions_column()
    Row = build_row_type([col], base=BaseRow)
    row = Row()
    row.repeat_duration_controls = False
    assert col.handler.on_interact(row, col.model, 5) is True
    assert row.route_repetitions == 5


def test_route_reps_handler_switch_back_from_duration_on_confirm(monkeypatch):
    import pluggable_protocol_tree.builtins.route_repetitions_column as mod
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: mod.YES)
    col = mod.make_route_repetitions_column()
    Row = build_row_type([col], base=BaseRow)
    row = Row()
    row.repeat_duration_controls = True
    assert col.handler.on_interact(row, col.model, 3) is True
    assert row.repeat_duration_controls is False     # handed back to count mode
    assert row.route_repetitions == 3


def test_route_reps_handler_cancel_rejects_edit(monkeypatch):
    import pluggable_protocol_tree.builtins.route_repetitions_column as mod
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: 0)   # not YES
    col = mod.make_route_repetitions_column()
    Row = build_row_type([col], base=BaseRow)
    row = Row()
    row.repeat_duration_controls = True
    row.route_repetitions = 1
    assert col.handler.on_interact(row, col.model, 9) is False
    assert row.repeat_duration_controls is True          # unchanged
    assert row.route_repetitions == 1                    # edit rejected

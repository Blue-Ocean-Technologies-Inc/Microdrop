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

"""Tests for base column views.

Focused on the non-Qt surface: format_display, get_flags, get_check_state.
create_editor is exercised in the widget-level smoke test (Task 27).
"""

from pluggable_protocol_tree.models.row import BaseRow, GroupRow
from pluggable_protocol_tree.views.columns.base import BaseColumnView


def test_base_view_default_hints():
    v = BaseColumnView()
    assert v.hidden_by_default is False
    assert v.renders_on_group is True


def test_base_view_format_display_is_str_of_value():
    v = BaseColumnView()
    assert v.format_display(42, BaseRow()) == "42"
    assert v.format_display("hello", BaseRow()) == "hello"


def test_base_view_format_display_empty_for_none():
    v = BaseColumnView()
    assert v.format_display(None, BaseRow()) == ""


def test_base_view_get_check_state_returns_none():
    v = BaseColumnView()
    assert v.get_check_state(True, BaseRow()) is None


# --- StringEditColumnView ---

from pluggable_protocol_tree.views.columns.string_edit import StringEditColumnView


def test_string_edit_is_editable_on_step():
    v = StringEditColumnView()
    from pyface.qt.QtCore import Qt
    flags = v.get_flags(BaseRow())
    assert flags & Qt.ItemIsEditable


def test_string_edit_group_flags_default_editable_too():
    """StringEdit renders on groups by default (renders_on_group=True).

    A column that shouldn't be editable on groups — like Duration —
    overrides get_flags or sets renders_on_group=False."""
    v = StringEditColumnView()
    from pyface.qt.QtCore import Qt
    flags = v.get_flags(GroupRow())
    assert flags & Qt.ItemIsEditable


# --- SpinBox views ---

from pluggable_protocol_tree.views.columns.spinbox import (
    IntSpinBoxColumnView, DoubleSpinBoxColumnView,
)


def test_double_spinbox_stores_hints():
    v = DoubleSpinBoxColumnView(low=0.0, high=200.0, decimals=2, single_step=0.5)
    assert v.low == 0.0
    assert v.high == 200.0
    assert v.decimals == 2
    assert v.single_step == 0.5


def test_double_spinbox_format_display_applies_decimals():
    v = DoubleSpinBoxColumnView(decimals=2)
    assert v.format_display(3.14159, BaseRow()) == "3.14"


def test_double_spinbox_format_display_empty_for_none():
    v = DoubleSpinBoxColumnView()
    assert v.format_display(None, BaseRow()) == ""


def test_double_spinbox_group_is_not_editable():
    """Values on groups aren't meaningful for a per-step numeric column."""
    v = DoubleSpinBoxColumnView()
    from pyface.qt.QtCore import Qt
    flags = v.get_flags(GroupRow())
    assert not (flags & Qt.ItemIsEditable)


def test_int_spinbox_format_display_integer():
    v = IntSpinBoxColumnView()
    assert v.format_display(5, BaseRow()) == "5"
    assert v.format_display(5.9, BaseRow()) == "5"   # int cast


# --- CheckboxColumnView ---

from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView


def test_checkbox_display_is_empty_string():
    v = CheckboxColumnView()
    assert v.format_display(True, BaseRow()) == ""
    assert v.format_display(False, BaseRow()) == ""


def test_checkbox_check_state_on_step():
    from pyface.qt.QtCore import Qt
    v = CheckboxColumnView()
    assert v.get_check_state(True, BaseRow()) == Qt.Checked
    assert v.get_check_state(False, BaseRow()) == Qt.Unchecked


def test_checkbox_no_check_state_on_group():
    """Groups don't render the checkbox."""
    v = CheckboxColumnView()
    assert v.get_check_state(True, GroupRow()) is None


def test_checkbox_group_not_user_checkable():
    from pyface.qt.QtCore import Qt
    v = CheckboxColumnView()
    flags = v.get_flags(GroupRow())
    assert not (flags & Qt.ItemIsUserCheckable)


# --- ReadOnlyLabelColumnView ---

from pluggable_protocol_tree.views.columns.readonly_label import ReadOnlyLabelColumnView


def test_readonly_label_flags_not_editable():
    from pyface.qt.QtCore import Qt
    v = ReadOnlyLabelColumnView()
    assert not (v.get_flags(BaseRow()) & Qt.ItemIsEditable)


def test_readonly_label_create_editor_returns_none():
    v = ReadOnlyLabelColumnView()
    assert v.create_editor(None, None) is None

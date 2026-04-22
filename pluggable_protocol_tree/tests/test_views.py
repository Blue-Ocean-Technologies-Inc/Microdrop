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

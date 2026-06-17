"""Tests for persisting protocol-tree column visibility across restarts.

Visibility lives in ProtocolPreferences.protocol_tree_column_visibility
(#420 retired the standalone JSON store). Covers the preference round-trip
across helper instances sharing one preferences node, plus the
ProtocolTreeWidget wiring (restore on construction, persist on toggle,
fall back to hidden_by_default for columns with no saved entry).
"""

import pytest

from apptools.preferences.api import Preferences

from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


@pytest.fixture
def prefs_node():
    """Isolated in-memory preferences node (no on-disk state shared
    between tests)."""
    return Preferences()


@pytest.fixture
def prefs(prefs_node):
    return ProtocolPreferences(preferences=prefs_node)


def _index_of(manager, col_name):
    for i, col in enumerate(manager.columns):
        if col.model.col_name == col_name:
            return i
    raise AssertionError(f"column {col_name!r} not found")


# --- preference round-trip -------------------------------------------------

def test_preference_defaults_to_empty_map(prefs):
    assert prefs.protocol_tree_column_visibility == {}


def test_preference_round_trip_across_helper_instances(prefs, prefs_node):
    prefs.protocol_tree_column_visibility = {"name": False, "trail_length": True}
    # A fresh helper against the same node sees the persisted map —
    # i.e. the value survives "restart" (helper reconstruction).
    reread = ProtocolPreferences(preferences=prefs_node)
    assert reread.protocol_tree_column_visibility == {
        "name": False, "trail_length": True,
    }


# --- widget wiring -------------------------------------------------------

def test_widget_uses_defaults_when_no_saved_state(qapp, prefs):
    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager, preferences=prefs)

    name_i = _index_of(manager, make_name_column().model.col_name)
    trail_i = _index_of(manager, make_trail_length_column().model.col_name)

    assert widget.tree.isColumnHidden(name_i) is False
    assert widget.tree.isColumnHidden(trail_i) is True  # hidden_by_default


def test_widget_restores_persisted_visibility(qapp, prefs):
    name_col = make_name_column().model.col_name
    trail_col = make_trail_length_column().model.col_name
    # Opposite of the defaults: hide Name, show the hidden-by-default Trail.
    prefs.protocol_tree_column_visibility = {name_col: False, trail_col: True}

    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager, preferences=prefs)

    assert widget.tree.isColumnHidden(_index_of(manager, name_col)) is True
    assert widget.tree.isColumnHidden(_index_of(manager, trail_col)) is False


def test_toggle_persists_full_visibility_map(qapp, prefs):
    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager, preferences=prefs)

    # Reveal the hidden-by-default column, then persist as the menu does.
    widget.tree.setColumnHidden(_index_of(manager, "Trail Len"), False)
    widget._persist_column_visibility()

    assert prefs.protocol_tree_column_visibility == {
        "name": True, "trail_length": True,
    }

"""Tests for persisting protocol-tree column ORDER across restarts.

Order lives in ProtocolPreferences.protocol_tree_column_order as a list of
col_id in visual (left-to-right) order. Mirrors the visibility persistence:
the preference round-trips across helper instances sharing one preferences
node, and the ProtocolTreeWidget restores the order on construction and
persists it whenever the user drags a header section (sectionMoved). Order is
keyed by the stable col_id, independent of visibility, and tolerant of columns
added/removed between sessions.
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


def _logical_of(manager, col_id):
    for i, col in enumerate(manager.columns):
        if col.model.col_id == col_id:
            return i
    raise AssertionError(f"column {col_id!r} not found")


# --- preference round-trip -------------------------------------------------

def test_order_preference_defaults_to_empty_list(prefs):
    assert prefs.protocol_tree_column_order == []


def test_order_preference_round_trip_across_helper_instances(prefs, prefs_node):
    prefs.protocol_tree_column_order = ["trail_length", "name"]
    # A fresh helper against the same node sees the persisted order —
    # i.e. the value survives "restart" (helper reconstruction).
    reread = ProtocolPreferences(preferences=prefs_node)
    assert reread.protocol_tree_column_order == ["trail_length", "name"]


# --- widget wiring -------------------------------------------------------

def test_widget_keeps_natural_order_when_nothing_saved(qapp, prefs):
    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager, preferences=prefs)
    header = widget.tree.header()
    # Visual order matches logical order (no reordering applied).
    assert header.visualIndex(_logical_of(manager, "name")) == 0
    assert header.visualIndex(_logical_of(manager, "trail_length")) == 1


def test_widget_restores_persisted_order(qapp, prefs):
    # Reverse of the natural order: Trail first, Name second.
    prefs.protocol_tree_column_order = ["trail_length", "name"]

    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager, preferences=prefs)
    header = widget.tree.header()

    assert header.visualIndex(_logical_of(manager, "trail_length")) == 0
    assert header.visualIndex(_logical_of(manager, "name")) == 1


def test_widget_appends_unsaved_columns_at_end(qapp, prefs):
    # Only Trail saved; Name (added/unknown to the saved order) must keep a
    # position — appended after the saved columns rather than dropped.
    prefs.protocol_tree_column_order = ["trail_length"]

    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager, preferences=prefs)
    header = widget.tree.header()

    assert header.visualIndex(_logical_of(manager, "trail_length")) == 0
    assert header.visualIndex(_logical_of(manager, "name")) == 1


def test_dragging_section_persists_full_order(qapp, prefs):
    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager, preferences=prefs)

    # Move the section at visual 0 (Name) to visual 1 — same as a header drag.
    # sectionMoved is wired, so this auto-persists the new visual order.
    widget.tree.header().moveSection(0, 1)

    assert prefs.protocol_tree_column_order == ["trail_length", "name"]

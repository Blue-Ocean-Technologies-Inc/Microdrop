"""Tests for the electrodes and routes columns + RoutesHandler.
electrodes/routes are read-only summary cells; the actual edit path is
the demo's SimpleDeviceViewer (and tests / programmatic mutation)."""

from pyface.qt.QtCore import Qt

from pluggable_protocol_tree.models.row import BaseRow, build_row_type
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)


# --- electrodes column ---

def test_electrodes_column_metadata():
    col = make_electrodes_column()
    assert col.model.col_id == "electrodes"
    assert col.model.col_name == "Electrodes"
    assert col.model.default_value == []


def test_electrodes_column_trait_defaults_to_empty_list():
    col = make_electrodes_column()
    RowType = build_row_type([col], base=BaseRow)
    r = RowType()
    assert r.electrodes == []


def test_electrodes_summary_shows_pluralized_count():
    col = make_electrodes_column()
    assert col.view.format_display([], BaseRow()) == "0 electrodes"
    assert col.view.format_display(["e0"], BaseRow()) == "1 electrode"
    assert col.view.format_display(["e0", "e1", "e2"], BaseRow()) == "3 electrodes"


def test_electrodes_summary_handles_none_value():
    """Defensive: if the underlying value is somehow None, render as 0."""
    col = make_electrodes_column()
    assert col.view.format_display(None, BaseRow()) == "0 electrodes"


def test_electrodes_cell_is_not_editable():
    col = make_electrodes_column()
    assert not (col.view.get_flags(BaseRow()) & Qt.ItemIsEditable)


def test_electrodes_cell_create_editor_returns_none():
    col = make_electrodes_column()
    assert col.view.create_editor(None, None) is None

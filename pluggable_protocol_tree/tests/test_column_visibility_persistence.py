"""Tests for persisting protocol-tree column visibility across restarts.

Covers the standalone store (save/load round-trip, graceful degradation)
and the ProtocolTreeWidget wiring (restore on construction, persist on
toggle, fall back to hidden_by_default for columns with no saved entry).
"""

import pytest

from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services import column_visibility_store as store
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    """Redirect the store's per-user config dir at a temp path."""
    monkeypatch.setattr(store.ETSConfig, "application_home", str(tmp_path))
    return tmp_path


def _index_of(manager, col_name):
    for i, col in enumerate(manager.columns):
        if col.model.col_name == col_name:
            return i
    raise AssertionError(f"column {col_name!r} not found")


# --- store ---------------------------------------------------------------

def test_load_returns_empty_when_no_file(config_home):
    assert store.load_column_visibility() == {}


def test_save_load_round_trip(config_home):
    store.save_column_visibility({"Name": False, "Trail Len": True})
    assert store.load_column_visibility() == {"Name": False, "Trail Len": True}


def test_load_ignores_malformed_file(config_home):
    store._settings_path().write_text("not json", encoding="utf-8")
    assert store.load_column_visibility() == {}


def test_load_ignores_non_dict_json(config_home):
    store._settings_path().write_text("[1, 2, 3]", encoding="utf-8")
    assert store.load_column_visibility() == {}


# --- widget wiring -------------------------------------------------------

def test_widget_uses_defaults_when_no_saved_state(qapp, config_home):
    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager)

    name_i = _index_of(manager, make_name_column().model.col_name)
    trail_i = _index_of(manager, make_trail_length_column().model.col_name)

    assert widget.tree.isColumnHidden(name_i) is False
    assert widget.tree.isColumnHidden(trail_i) is True  # hidden_by_default


def test_widget_restores_persisted_visibility(qapp, config_home):
    name_col = make_name_column().model.col_name
    trail_col = make_trail_length_column().model.col_name
    # Opposite of the defaults: hide Name, show the hidden-by-default Trail.
    store.save_column_visibility({name_col: False, trail_col: True})

    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager)

    assert widget.tree.isColumnHidden(_index_of(manager, name_col)) is True
    assert widget.tree.isColumnHidden(_index_of(manager, trail_col)) is False


def test_toggle_persists_full_visibility_map(qapp, config_home):
    name_col = make_name_column().model.col_name
    trail_col = make_trail_length_column().model.col_name

    manager = RowManager(columns=[make_name_column(), make_trail_length_column()])
    widget = ProtocolTreeWidget(manager)

    # Reveal the hidden-by-default column, then persist as the menu does.
    widget.tree.setColumnHidden(_index_of(manager, trail_col), False)
    widget._persist_column_visibility()

    saved = store.load_column_visibility()
    assert saved == {name_col: True, trail_col: True}

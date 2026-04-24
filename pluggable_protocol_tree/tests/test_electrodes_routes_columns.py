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


# --- routes column + RoutesHandler ---

import json
from unittest.mock import MagicMock, patch

from pluggable_protocol_tree.builtins.routes_column import (
    make_routes_column, RoutesHandler,
)
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)


def test_routes_column_metadata():
    col = make_routes_column()
    assert col.model.col_id == "routes"
    assert col.model.col_name == "Routes"
    assert col.model.default_value == []


def test_routes_column_trait_defaults_to_empty_list():
    col = make_routes_column()
    RowType = build_row_type([col], base=BaseRow)
    r = RowType()
    assert r.routes == []


def test_routes_summary_shows_pluralized_count():
    col = make_routes_column()
    assert col.view.format_display([], BaseRow()) == "0 routes"
    assert col.view.format_display([["a", "b"]], BaseRow()) == "1 route"
    assert col.view.format_display(
        [["a", "b"], ["c", "d"], ["e", "f"]], BaseRow()
    ) == "3 routes"


def test_routes_cell_is_not_editable():
    col = make_routes_column()
    assert not (col.view.get_flags(BaseRow()) & Qt.ItemIsEditable)


def test_routes_handler_default_priority_and_wait_topics():
    """Priority 30 keeps it earlier than DurationColumnHandler (90)."""
    h = RoutesHandler()
    assert h.priority == 30
    assert ELECTRODES_STATE_APPLIED in h.wait_for_topics


def test_routes_handler_publishes_each_phase_then_waits():
    """Build a row with electrodes=['e0','e1'] + routes=[['e2','e3','e4']]
    + trail_length=1; the handler should publish 3 phases (one per
    route position, each unioned with the static electrodes), and
    ctx.wait_for between each."""
    col = make_routes_column()
    RowType = build_row_type([col], base=BaseRow)
    row = RowType()
    row.electrodes = ["e0", "e1"]
    row.routes = [["e2", "e3", "e4"]]
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 0.0
    row.linear_repeats = False
    row.duration_s = 0.0     # no per-phase dwell so the unit test stays fast
    row.repetitions = 1

    ctx = MagicMock()
    # MagicMock returns a truthy Mock for any attribute access; the
    # handler bails on stop_event.is_set() being truthy. Pin it to a
    # real falsy callable so the publish loop runs to completion.
    ctx.protocol.stop_event.is_set.return_value = False
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {
        "e0": 0, "e1": 1, "e2": 2, "e3": 3, "e4": 4,
    }}

    published = []
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               side_effect=lambda **kw: published.append(kw)):
        col.handler.on_step(row, ctx)

    # 3 publishes, 3 wait_for calls (one between each)
    assert len(published) == 3
    assert ctx.wait_for.call_count == 3
    # Each publish targets ELECTRODES_STATE_CHANGE
    assert all(p["topic"] == ELECTRODES_STATE_CHANGE for p in published)
    # Payloads are JSON envelopes carrying electrodes + channels
    payloads = [json.loads(p["message"]) for p in published]
    assert payloads[0]["electrodes"] == ["e0", "e1", "e2"]
    assert payloads[0]["channels"] == [0, 1, 2]
    assert payloads[1]["electrodes"] == ["e0", "e1", "e3"]
    assert payloads[2]["electrodes"] == ["e0", "e1", "e4"]


def test_routes_handler_unmapped_electrode_logs_warning_and_skips_channel():
    """If an electrode in the phase isn't in electrode_to_channel, the
    payload's `channels` array doesn't include it (skipped silently
    aside from a logger.warning). The `electrodes` list still does."""
    col = make_routes_column()
    RowType = build_row_type([col], base=BaseRow)
    row = RowType()
    row.electrodes = []
    row.routes = [["unknown_electrode"]]
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 0.0
    row.linear_repeats = False
    row.duration_s = 0.0
    row.repetitions = 1

    ctx = MagicMock()
    ctx.protocol.stop_event.is_set.return_value = False
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {}}

    published = []
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               side_effect=lambda **kw: published.append(kw)):
        col.handler.on_step(row, ctx)

    assert len(published) == 1
    payload = json.loads(published[0]["message"])
    assert payload["electrodes"] == ["unknown_electrode"]
    assert payload["channels"] == []

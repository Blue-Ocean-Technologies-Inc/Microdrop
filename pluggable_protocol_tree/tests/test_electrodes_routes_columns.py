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


def test_routes_handler_publishes_display_and_hardware_per_phase():
    """Build a row with electrodes=['e0','e1'] + routes=[['e2','e3','e4']]
    + trail_length=1; the handler should publish 3 phases. Each phase
    emits TWO messages — PROTOCOL_TREE_DISPLAY_STATE (display path) and
    ELECTRODES_STATE_CHANGE (hardware path) — and waits for the
    hardware ack once per phase. Matches the legacy protocol_grid
    split between display and hardware.
    """
    from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )

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
    ctx.protocol.stop_event.is_set.return_value = False
    ctx.protocol.preview_mode = False
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {
        "e0": 0, "e1": 1, "e2": 2, "e3": 3, "e4": 4,
    }}

    published = []
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               side_effect=lambda **kw: published.append(kw)):
        col.handler.on_step(row, ctx)

    # 3 phases * 2 messages (display + hardware) = 6 publishes
    assert len(published) == 6
    # 3 hardware-ack waits (only the hardware messages need ack)
    assert ctx.wait_for.call_count == 3

    display_msgs = [p for p in published if p["topic"] == PROTOCOL_TREE_DISPLAY_STATE]
    hardware_msgs = [p for p in published if p["topic"] == ELECTRODES_STATE_CHANGE]
    assert len(display_msgs) == 3
    assert len(hardware_msgs) == 3

    # Hardware payloads — sorted electrodes + channels
    hw_payloads = [json.loads(p["message"]) for p in hardware_msgs]
    assert hw_payloads[0]["electrodes"] == ["e0", "e1", "e2"]
    assert hw_payloads[0]["channels"] == [0, 1, 2]
    assert hw_payloads[1]["electrodes"] == ["e0", "e1", "e3"]
    assert hw_payloads[2]["electrodes"] == ["e0", "e1", "e4"]

    # Display payloads — same electrode list, plus the row's static
    # routes / step_label / editable=False.
    disp_payloads = [
        ProtocolTreeDisplayMessage.deserialize(p["message"])
        for p in display_msgs
    ]
    assert disp_payloads[0].electrodes == ["e0", "e1", "e2"]
    assert disp_payloads[1].electrodes == ["e0", "e1", "e3"]
    assert disp_payloads[2].electrodes == ["e0", "e1", "e4"]
    for m in disp_payloads:
        assert m.routes == [["e2", "e3", "e4"]]
        assert m.editable is False
        assert m.free_mode is False


def test_routes_handler_preview_mode_skips_hardware_and_ack():
    """Preview mode: the display path still fires (so the DV animates
    the phases) but ELECTRODES_STATE_CHANGE is NOT published and we
    do NOT wait for an ack. Critical because in preview there's often
    no hardware listener, so a wait would stall 5s per phase.
    """
    from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE

    col = make_routes_column()
    RowType = build_row_type([col], base=BaseRow)
    row = RowType()
    row.electrodes = ["e0"]
    row.routes = [["e1", "e2"]]
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
    ctx.protocol.preview_mode = True
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {
        "e0": 0, "e1": 1, "e2": 2,
    }}

    published = []
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               side_effect=lambda **kw: published.append(kw)):
        col.handler.on_step(row, ctx)

    # All published messages are display-only — none target the
    # hardware topic.
    assert all(p["topic"] == PROTOCOL_TREE_DISPLAY_STATE for p in published)
    assert not any(p["topic"] == ELECTRODES_STATE_CHANGE for p in published)
    # And we never blocked on a hardware ack.
    assert ctx.wait_for.call_count == 0


def test_routes_handler_unmapped_electrode_logs_warning_and_skips_channel():
    """If an electrode in the phase isn't in electrode_to_channel, the
    hardware payload's ``channels`` array skips it (silent aside from a
    logger.warning). The ``electrodes`` list still includes it."""
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
    ctx.protocol.preview_mode = False
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {}}

    published = []
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               side_effect=lambda **kw: published.append(kw)):
        col.handler.on_step(row, ctx)

    # 1 display + 1 hardware
    hardware_msgs = [p for p in published if p["topic"] == ELECTRODES_STATE_CHANGE]
    assert len(hardware_msgs) == 1
    payload = json.loads(hardware_msgs[0]["message"])
    assert payload["electrodes"] == ["unknown_electrode"]
    assert payload["channels"] == []


def test_routes_handler_uses_route_repetitions_for_loop_count():
    """iter_phases must receive n_repeats from route_repetitions, NOT
    repetitions (which now only drives whole-step expansion)."""
    from unittest.mock import MagicMock, patch
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.routes_column import make_routes_column
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )

    col = make_routes_column()
    Row = build_row_type([col, make_route_repetitions_column()], base=BaseRow)
    row = Row()
    row.routes = [["a", "b", "c", "a"]]
    row.route_repetitions = 3
    row.repetitions = 7          # must be IGNORED by phase generation
    row.duration_s = 0.0         # zero dwell so the test is instant

    ctx = MagicMock()
    ctx.protocol.stop_event.is_set.return_value = False
    ctx.protocol.pause_event.is_set.return_value = False
    ctx.protocol.preview_mode = True     # skip hardware publish + ack wait
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {"a": 0, "b": 1, "c": 2}}

    captured = {}
    import pluggable_protocol_tree.builtins.routes_column as mod
    real_iter = mod.iter_phases

    def spy(*args, **kwargs):
        captured["n_repeats"] = kwargs.get("n_repeats")
        return real_iter(*args, **kwargs)

    with patch.object(mod, "iter_phases", side_effect=spy), \
         patch.object(mod, "publish_message", lambda **kw: None):
        col.handler.on_step(row, ctx)

    assert captured["n_repeats"] == 3


def test_routes_handler_hold_pad_uses_total_emitted_phase_count():
    """Pad = repeat_duration - len(phases)*dwell, based on the ACTUAL
    emitted phases (so loop cycles + soft ramps + open routes all count).
    iter_phases is patched to a known 6-phase list; T=10, dwell=1 => pad 4."""
    from unittest.mock import MagicMock, patch
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.routes_column import (
        make_routes_column, DURATION_CONSUMED_KEY,
    )
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    import pluggable_protocol_tree.builtins.routes_column as mod

    col = make_routes_column()
    Row = build_row_type([col, make_route_repetitions_column()], base=BaseRow)
    row = Row()
    row.routes = [["a", "b", "c", "a"]]
    row.duration_s = 1.0
    row.repeat_duration = 10.0
    row.repeat_duration_controls = True

    fake_phases = [{"a"}, {"a", "b"}, {"a", "b", "c"}, {"a", "b"}, {"a"}, {"a"}]

    ctx = MagicMock()
    ctx.protocol.stop_event.is_set.return_value = False
    ctx.protocol.pause_event.is_set.return_value = False
    ctx.protocol.preview_mode = True
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {"a": 0, "b": 1, "c": 2}}

    sleeps = []
    with patch.object(mod, "publish_message", lambda **kw: None), \
         patch.object(mod, "iter_phases", return_value=iter(fake_phases)), \
         patch.object(mod, "_cooperative_sleep",
                      side_effect=lambda secs, *a, **k: sleeps.append(secs)):
        col.handler.on_step(row, ctx)

    # 6 per-phase dwells of 1.0, then the pad of 10 - 6*1 = 4.0.
    assert sleeps[-1] == 4.0
    assert sum(sleeps) == 10.0          # total lands exactly on the budget
    assert ctx.scratch.get(DURATION_CONSUMED_KEY) is True


def test_routes_handler_no_hold_pad_in_count_mode():
    """Count mode (repeat_duration_controls False): no extra pad sleep —
    only the per-phase dwells occur."""
    from unittest.mock import MagicMock, patch
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.routes_column import make_routes_column
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    import pluggable_protocol_tree.builtins.routes_column as mod

    col = make_routes_column()
    Row = build_row_type([col, make_route_repetitions_column()], base=BaseRow)
    row = Row()
    row.routes = [["a", "b", "c", "a"]]
    row.duration_s = 1.0
    row.repeat_duration = 10.0
    row.repeat_duration_controls = False     # count mode

    fake_phases = [{"a"}, {"a", "b"}, {"a", "b", "c"}, {"a", "b"}, {"a"}, {"a"}]

    ctx = MagicMock()
    ctx.protocol.stop_event.is_set.return_value = False
    ctx.protocol.pause_event.is_set.return_value = False
    ctx.protocol.preview_mode = True
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {"a": 0, "b": 1, "c": 2}}

    sleeps = []
    with patch.object(mod, "publish_message", lambda **kw: None), \
         patch.object(mod, "iter_phases", return_value=iter(fake_phases)), \
         patch.object(mod, "_cooperative_sleep",
                      side_effect=lambda secs, *a, **k: sleeps.append(secs)):
        col.handler.on_step(row, ctx)

    # Exactly one sleep per phase, no trailing pad sleep.
    assert len(sleeps) == len(fake_phases)


def test_routes_handler_no_pad_sleep_when_phases_fill_budget():
    """Duration mode but len(phases)*dwell == repeat_duration: pad is 0 so
    no extra sleep is added beyond the per-phase dwells."""
    from unittest.mock import MagicMock, patch
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.routes_column import make_routes_column
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    import pluggable_protocol_tree.builtins.routes_column as mod

    col = make_routes_column()
    Row = build_row_type([col, make_route_repetitions_column()], base=BaseRow)
    row = Row()
    row.routes = [["a", "b", "c", "a"]]
    row.duration_s = 1.0
    row.repeat_duration = 6.0                # equals 6 phases * 1.0
    row.repeat_duration_controls = True

    fake_phases = [{"a"}, {"a", "b"}, {"a", "b", "c"}, {"a", "b"}, {"a"}, {"a"}]

    ctx = MagicMock()
    ctx.protocol.stop_event.is_set.return_value = False
    ctx.protocol.pause_event.is_set.return_value = False
    ctx.protocol.preview_mode = True
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {"a": 0, "b": 1, "c": 2}}

    sleeps = []
    with patch.object(mod, "publish_message", lambda **kw: None), \
         patch.object(mod, "iter_phases", return_value=iter(fake_phases)), \
         patch.object(mod, "_cooperative_sleep",
                      side_effect=lambda secs, *a, **k: sleeps.append(secs)):
        col.handler.on_step(row, ctx)

    assert len(sleeps) == len(fake_phases)   # no extra pad sleep (pad == 0)

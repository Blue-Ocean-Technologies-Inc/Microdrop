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


def _captured_repeat_duration_s(controls):
    """Run RoutesHandler.on_step and return the repeat_duration_s that
    was passed into iter_phases, for a row with repeat_duration=7.0 and
    repeat_duration_controls=`controls`."""
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
    row.duration_s = 0.0
    row.repeat_duration = 7.0
    row.route_repetitions = 1
    row.repeat_duration_controls = controls

    ctx = MagicMock()
    ctx.protocol.stop_event.is_set.return_value = False
    ctx.protocol.pause_event.is_set.return_value = False
    ctx.protocol.preview_mode = True
    ctx.scratch = {}
    ctx.protocol.scratch = {"electrode_to_channel": {"a": 0, "b": 1, "c": 2}}

    seen = {}
    real = mod.iter_phases

    def spy(*a, **k):
        seen["rd"] = k.get("repeat_duration_s")
        return real(*a, **k)

    with patch.object(mod, "iter_phases", side_effect=spy), \
         patch.object(mod, "publish_message", lambda **kw: None):
        col.handler.on_step(row, ctx)
    return seen["rd"]


def test_routes_handler_duration_mode_gated_on_controls_flag():
    """Phase generation must enter duration mode ONLY when
    repeat_duration_controls is True. In count mode (flag False) a
    non-zero repeat_duration (e.g. the auto-estimate) must NOT truncate
    the loop: iter_phases receives repeat_duration_s=0 so
    route_repetitions drives the cycle count. Otherwise the loop is
    truncated to the budget WITHOUT the compensating hold-pad (which is
    also gated on the flag), making the step run short."""
    assert _captured_repeat_duration_s(controls=False) == 0.0   # count mode
    assert _captured_repeat_duration_s(controls=True) == 7.0     # duration mode


def test_cooperative_sleep_returns_early_on_phase_advance_event():
    """_cooperative_sleep wakes promptly when phase_advance_event is set,
    same shape as the existing stop_event wake — return cleanly (do NOT
    raise)."""
    import threading
    import time
    from pluggable_protocol_tree.builtins.routes_column import (
        _cooperative_sleep,
    )
    stop_event = threading.Event()
    pause_event = None
    advance_event = threading.Event()

    def _set_after(delay):
        time.sleep(delay)
        advance_event.set()

    threading.Thread(target=_set_after, args=(0.05,), daemon=True).start()
    t0 = time.monotonic()
    # 5 second dwell, but the advance_event fires at ~50 ms
    _cooperative_sleep(5.0, stop_event, pause_event,
                       phase_advance_event=advance_event)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, f"expected early return, elapsed={elapsed:.2f}s"


def test_cooperative_sleep_phase_advance_event_kwarg_is_optional():
    """Callers that don't care about phase early-advance can omit the
    kwarg and get the original behaviour."""
    import threading
    import time
    from pluggable_protocol_tree.builtins.routes_column import (
        _cooperative_sleep,
    )
    stop_event = threading.Event()
    t0 = time.monotonic()
    _cooperative_sleep(0.1, stop_event, None)
    elapsed = time.monotonic() - t0
    assert 0.05 <= elapsed < 0.5      # roughly the requested dwell


def test_routes_handler_clears_phase_advance_event_each_iteration(qapp):
    """RoutesHandler must clear the event at the TOP of each phase loop
    iteration so a set from phase N doesn't leak into phase N+1."""
    from unittest.mock import MagicMock, patch
    import threading
    from pluggable_protocol_tree.builtins.routes_column import (
        RoutesHandler,
    )

    handler = RoutesHandler()
    advance_event = threading.Event()
    advance_event.set()                # simulate stale set from prior phase

    row = MagicMock()
    row.routes = []                    # no routes -> single static phase
    row.electrodes = ["e1"]
    row.duration_s = 0.001
    row.route_repetitions = 1
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 0.0
    row.repeat_duration_controls = False
    row.linear_repeats = False
    row.volume_threshold = 0           # no VT -> static path
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True          # skip hardware publish + ack wait
    proto.scratch = {"electrode_to_channel": {"e1": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = advance_event
    ctx.step_phases_done_event = threading.Event()
    ctx.wait_for = MagicMock()

    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               lambda **kw: None):
        handler.on_step(row, ctx)
    # Even though the test pre-set the event, RoutesHandler must clear
    # it before entering the dwell (otherwise the single-phase wouldn't
    # actually sleep). Confirm by asserting the event ended up CLEARED
    # after on_step returns (Routes also has nothing left to set after
    # the loop exits).
    assert advance_event.is_set() is False


def test_routes_handler_sets_step_phases_done_event_when_loop_finishes(qapp):
    """After Routes finishes its per-phase loop (and any in-duration-mode
    hold), step_phases_done_event must be set so sibling handlers can
    exit their wait loops."""
    from unittest.mock import MagicMock, patch
    import threading
    from pluggable_protocol_tree.builtins.routes_column import (
        RoutesHandler,
    )

    handler = RoutesHandler()
    row = MagicMock()
    row.routes = []
    row.electrodes = ["e1"]
    row.duration_s = 0.001
    row.route_repetitions = 1
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 0.0
    row.repeat_duration_controls = False
    row.linear_repeats = False
    row.volume_threshold = 0           # no VT -> static path
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True
    proto.scratch = {"electrode_to_channel": {"e1": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.wait_for = MagicMock()

    assert ctx.step_phases_done_event.is_set() is False
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               lambda **kw: None):
        handler.on_step(row, ctx)
    assert ctx.step_phases_done_event.is_set() is True


def test_dynamic_vt_loop_runs_more_cycles_than_precalc(qapp):
    """Duration mode + volume_threshold > 0: the handler loops the unit
    cycle dynamically based on a fake clock that advances slower than the
    full per-phase dwell (simulating VT cutting phases short), running far
    more cycles than the precalc (budget / cycle_full_time) would.

    Deterministic clock: each phase advances the fake clock by 0.5s; the
    full per-phase dwell is 1.0s, so the precalc would do budget/cycle_time
    = 8/2 = 4 cycles, but the dynamic loop fits ~7."""
    from unittest.mock import MagicMock, patch
    import threading
    import pluggable_protocol_tree.builtins.routes_column as mod
    from pluggable_protocol_tree.builtins.routes_column import RoutesHandler

    handler = RoutesHandler()
    row = MagicMock()
    row.routes = [["a", "b", "a"]]      # loop route -> unit cycle [{a},{b}]
    row.electrodes = []
    row.duration_s = 1.0                # full per-phase dwell
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = True                 # MUST be ignored (ramp-down dropped)
    row.repeat_duration = 8.0
    row.repeat_duration_controls = True
    row.linear_repeats = False
    row.route_repetitions = 1
    row.volume_threshold = 50           # VT active
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True           # skip hardware publish + ack wait
    proto.scratch = {"electrode_to_channel": {"a": 0, "b": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.scratch = {}
    ctx.wait_for = MagicMock()

    clock = {"t": 0.0}

    def fake_sleep(secs, *a, **k):
        clock["t"] += 0.5               # each phase "really" takes 0.5s

    displays = []

    def fake_publish(**kw):
        from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
        if kw.get("topic") == PROTOCOL_TREE_DISPLAY_STATE:
            displays.append(kw)

    # iter_phases must NOT be used on the dynamic path.
    iter_spy = MagicMock(side_effect=AssertionError("iter_phases used on VT path"))

    with patch.object(mod, "_monotonic", lambda: clock["t"]), \
         patch.object(mod, "_cooperative_sleep", side_effect=fake_sleep), \
         patch.object(mod, "publish_message", side_effect=fake_publish), \
         patch.object(mod, "iter_phases", iter_spy):
        handler.on_step(row, ctx)

    # Unit cycle = 2 phases; loop runs while t + 2.0 <= 8.0 (t <= 6.0),
    # advancing 1.0/cycle -> cycles at t=0,1,2,3,4,5,6 = 7 cycles = 14
    # phases, plus the single return-to-start phase = 15 display publishes.
    assert len(displays) == 7 * 2 + 1   # 7 cycles x 2 phases + 1 return phase
    # Precalc equivalent would be 4 cycles + return = 9; dynamic ran more.
    assert len(displays) > 9
    assert ctx.step_phases_done_event.is_set() is True
    assert ctx.scratch.get(mod.DURATION_CONSUMED_KEY) is True


def test_dynamic_vt_loop_emits_running_index_with_zero_total(qapp):
    """Each phase emits phase_started with a monotonically increasing index
    and phase_total == 0 (unknown while looping)."""
    from unittest.mock import MagicMock, patch
    import threading
    import pluggable_protocol_tree.builtins.routes_column as mod
    from pluggable_protocol_tree.builtins.routes_column import RoutesHandler

    handler = RoutesHandler()
    row = MagicMock()
    row.routes = [["a", "b", "a"]]
    row.electrodes = []
    row.duration_s = 1.0
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 4.0
    row.repeat_duration_controls = True
    row.linear_repeats = False
    row.route_repetitions = 1
    row.volume_threshold = 50
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True
    proto.scratch = {"electrode_to_channel": {"a": 0, "b": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.scratch = {}
    ctx.wait_for = MagicMock()

    clock = {"t": 0.0}
    with patch.object(mod, "_monotonic", lambda: clock["t"]), \
         patch.object(mod, "_cooperative_sleep",
                      side_effect=lambda s, *a, **k: clock.__setitem__("t", clock["t"] + 0.5)), \
         patch.object(mod, "publish_message", lambda **kw: None):
        handler.on_step(row, ctx)

    calls = proto.qsignals.phase_started.emit.call_args_list
    indices = [c.args[0] for c in calls]
    totals = [c.args[1] for c in calls]
    assert indices == list(range(1, len(indices) + 1))   # 1,2,3,... no gaps
    assert all(t == 0 for t in totals)                   # total unknown


def test_dynamic_vt_loop_not_taken_when_no_volume_threshold(qapp):
    """Duration mode WITHOUT volume threshold: the static precalc path runs
    (iter_phases is used), proving the dynamic loop is gated on VT."""
    from unittest.mock import MagicMock, patch
    import threading
    import pluggable_protocol_tree.builtins.routes_column as mod
    from pluggable_protocol_tree.builtins.routes_column import RoutesHandler

    handler = RoutesHandler()
    row = MagicMock()
    row.routes = [["a", "b", "a"]]
    row.electrodes = []
    row.duration_s = 0.0
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 8.0
    row.repeat_duration_controls = True
    row.linear_repeats = False
    row.route_repetitions = 1
    row.volume_threshold = 0            # NO VT
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True
    proto.scratch = {"electrode_to_channel": {"a": 0, "b": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.scratch = {}
    ctx.wait_for = MagicMock()

    real_iter = mod.iter_phases
    iter_spy = MagicMock(side_effect=real_iter)
    with patch.object(mod, "iter_phases", iter_spy), \
         patch.object(mod, "publish_message", lambda **kw: None):
        handler.on_step(row, ctx)

    assert iter_spy.called          # precalc path used


def test_dynamic_vt_loop_static_only_repeats_within_budget(qapp):
    """Static-only step (no routes) + VT + duration mode: the single static
    phase is repeated within the budget; there is no return phase; the
    done event is still set. unit_cycle=[{a}] (cycle_full_time=1.0), budget
    4.0, clock +0.5/phase -> cycles at t=0,0.5,...,3.0 = 7 phases."""
    from unittest.mock import MagicMock, patch
    import threading
    import pluggable_protocol_tree.builtins.routes_column as mod
    from pluggable_protocol_tree.builtins.routes_column import RoutesHandler

    handler = RoutesHandler()
    row = MagicMock()
    row.routes = []                     # static-only
    row.electrodes = ["a"]
    row.duration_s = 1.0
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 4.0
    row.repeat_duration_controls = True
    row.linear_repeats = False
    row.route_repetitions = 1
    row.volume_threshold = 50
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True
    proto.scratch = {"electrode_to_channel": {"a": 0}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.scratch = {}
    ctx.wait_for = MagicMock()

    clock = {"t": 0.0}
    displays = []

    def fake_publish(**kw):
        from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
        if kw.get("topic") == PROTOCOL_TREE_DISPLAY_STATE:
            displays.append(kw)

    with patch.object(mod, "_monotonic", lambda: clock["t"]), \
         patch.object(mod, "_cooperative_sleep",
                      side_effect=lambda s, *a, **k: clock.__setitem__("t", clock["t"] + 0.5)), \
         patch.object(mod, "publish_message", side_effect=fake_publish):
        handler.on_step(row, ctx)

    # 7 repeats of the single static phase; no return phase (return_phase is None).
    assert len(displays) == 7
    assert ctx.step_phases_done_event.is_set() is True

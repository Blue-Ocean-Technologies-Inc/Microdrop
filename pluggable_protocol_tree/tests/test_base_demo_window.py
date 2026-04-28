"""Tests for the demo base window + DemoConfig + StatusReadout."""

import pytest

from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.demos.base_demo_window import (
    DemoConfig, StatusReadout, _slug,
)


def test_status_readout_required_fields():
    r = StatusReadout(label="Voltage", topic="dropbot/signals/voltage_applied",
                      fmt=lambda m: f"{int(m)} V")
    assert r.label == "Voltage"
    assert r.topic == "dropbot/signals/voltage_applied"
    assert r.fmt("100") == "100 V"
    assert r.initial == "--"   # default


def test_status_readout_initial_overridable():
    r = StatusReadout(label="Magnet", topic="x/applied",
                      fmt=lambda m: m, initial="idle")
    assert r.initial == "idle"


def test_demo_config_minimum_required_fields():
    cfg = DemoConfig(columns_factory=lambda: [])
    assert cfg.title == "Pluggable Protocol Tree Demo"
    assert cfg.window_size == (1100, 650)
    assert cfg.phase_ack_topic == ELECTRODES_STATE_APPLIED   # default
    assert cfg.status_readouts == []
    assert cfg.side_panel_factory is None


def test_demo_config_pre_populate_default_is_no_op():
    cfg = DemoConfig(columns_factory=lambda: [])
    cfg.pre_populate(None)   # must not raise


def test_demo_config_routing_setup_default_is_no_op():
    cfg = DemoConfig(columns_factory=lambda: [])
    cfg.routing_setup(None)


def test_demo_config_phase_ack_can_be_none():
    cfg = DemoConfig(columns_factory=lambda: [], phase_ack_topic=None)
    assert cfg.phase_ack_topic is None


def test_slug_lowercases_and_strips_punctuation():
    """slug('Voltage')='voltage'; slug('Magnet Height (mm)')='magnet_height_mm'."""
    assert _slug("Voltage") == "voltage"
    assert _slug("Magnet Height (mm)") == "magnet_height_mm"
    assert _slug("Step Time") == "step_time"


def test_slug_handles_empty_string():
    assert _slug("") == ""


def test_window_constructs_with_minimum_config(qapp):
    """Window builds successfully with just a columns_factory."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [
            make_type_column(), make_id_column(), make_name_column(),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w.windowTitle() == "Pluggable Protocol Tree Demo"
    # Has the manager + executor + tree widget wired
    assert w.manager is not None
    assert w.executor is not None
    assert w.widget is not None
    # Window size matches default
    assert (w.width(), w.height()) == (1100, 650)


def test_window_applies_custom_title_and_size(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        title="My Demo",
        window_size=(800, 500),
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w.windowTitle() == "My Demo"
    assert (w.width(), w.height()) == (800, 500)


def test_window_columns_match_factory_output(qapp):
    """RowManager has the columns returned by columns_factory."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [
        make_type_column(), make_id_column(), make_name_column(),
    ])
    w = BasePluggableProtocolDemoWindow(cfg)
    ids = [c.model.col_id for c in w.manager.columns]
    assert ids == ["type", "id", "name"]


def test_pre_populate_runs_after_manager_construction(qapp):
    """The pre_populate callback receives the live RowManager and
    rows added there are present after window construction."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )

    def populate(rm):
        rm.add_step(values={"name": "S1", "duration_s": 0.1})
        rm.add_step(values={"name": "S2", "duration_s": 0.2})

    cfg = DemoConfig(
        columns_factory=lambda: [
            make_type_column(), make_id_column(), make_name_column(),
            make_duration_column(),
        ],
        pre_populate=populate,
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    assert len(w.manager.root.children) == 2
    assert w.manager.root.children[0].name == "S1"
    assert w.manager.root.children[1].name == "S2"


def test_routing_setup_called_after_standard_chain(qapp, monkeypatch):
    """The routing_setup callback receives the router AFTER the base
    wires the PPT-3 electrode chain. Verify by recording the order."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )

    call_log = []

    def fake_router_setup_inner(self):
        # Replace the real broker setup with a recording fake.
        call_log.append("base_routing_setup")
        # Need to set self._router so routing_setup can be called with it.
        self._router = "fake-router"

    monkeypatch.setattr(
        BasePluggableProtocolDemoWindow,
        "_setup_dramatiq_routing_internal",
        fake_router_setup_inner,
    )

    def my_routing(router):
        call_log.append(("routing_setup", router))

    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        routing_setup=my_routing,
    )
    BasePluggableProtocolDemoWindow(cfg)
    assert call_log == ["base_routing_setup", ("routing_setup", "fake-router")]


def test_window_has_router_attribute_after_construction(qapp):
    """self._router exists (may be None if Redis unavailable, that's fine)."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    assert hasattr(w, "_router")


def test_window_has_status_bar_with_step_label(qapp):
    """Status bar exists with the step counter label."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    sb = w.statusBar()
    assert sb is not None
    # Step label and row label should be there.
    assert w._status_step_label.text() == "Idle"
    assert w._status_row_label.text() == ""


def test_window_status_step_elapsed_label_exists(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._status_step_time_label is not None


def test_window_executor_step_started_connected_to_tree_highlight(qapp):
    """The executor's step_started signal must connect to the tree
    widget's highlight_active_row slot — verifies the active-row
    highlight wiring is in place."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    # Indirect check: emit step_started with a fake row, watch tree's
    # highlight_active_row receive it.
    received = []
    orig = w.widget.highlight_active_row
    w.widget.highlight_active_row = lambda r: received.append(r)
    try:
        w.executor.qsignals.step_started.emit("fake-row")
        assert received == ["fake-row"]
    finally:
        w.widget.highlight_active_row = orig


def test_window_tick_timer_runs_at_10_hz(qapp):
    """Tick timer interval should be 100 ms (10 Hz)."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._tick_timer.interval() == 100


def test_phase_ack_topic_none_hides_phase_timer(qapp):
    """When phase_ack_topic=None, no phase elapsed label in status bar."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()],
                     phase_ack_topic=None)
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._status_phase_time_label is None


def test_phase_ack_topic_set_creates_phase_label(qapp):
    """When phase_ack_topic set, phase elapsed label is in status bar."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()],
                     phase_ack_topic="x/applied")
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._status_phase_time_label is not None


def test_phase_acked_signal_resets_phase_timer(qapp):
    """Emitting the phase_acked signal sets _phase_started_at = monotonic()."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()],
                     phase_ack_topic="x/applied")
    w = BasePluggableProtocolDemoWindow(cfg)
    # Set the current row so phase ack handler doesn't early-return.
    w._current_row = object()
    w._step_started_at = None
    before = w._phase_started_at
    w.phase_acked.emit()
    assert w._phase_started_at is not None
    assert w._phase_started_at != before
    # First ack also sets step_started_at if it was None.
    assert w._step_started_at is not None


def test_status_readout_creates_label_with_initial_text(qapp):
    """Each StatusReadout adds a QLabel with `<label>: <initial>` text."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        status_readouts=[
            StatusReadout("Voltage", "v/applied", lambda m: f"{int(m)} V"),
            StatusReadout("Frequency", "f/applied", lambda m: f"{int(m)} Hz"),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    labels = list(w._readout_labels.values())
    assert len(labels) == 2
    # Assertion order matches status_readouts declaration order (Python 3.7+ dict guarantee).
    assert labels[0].text() == "Voltage: --"
    assert labels[1].text() == "Frequency: --"


def test_status_readout_label_updates_on_signal(qapp):
    """Emitting the per-readout Qt signal updates the label text."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        status_readouts=[
            StatusReadout("Voltage", "v/applied", lambda m: f"{int(m)} V"),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    w._readout_signals["voltage"].emit("100")
    assert w._readout_labels["voltage"].text() == "Voltage: 100 V"


def test_status_readout_actor_names_are_slug_prefixed(qapp):
    """Each readout's auto-registered Dramatiq actor uses the slug-based
    naming convention. Verify by inspecting the broker's registered actors."""
    import dramatiq
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        status_readouts=[
            StatusReadout("Magnet Height (mm)", "m/applied",
                          lambda m: f"{m} mm"),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    # Actor name = ppt12_demo_<slug>_listener
    expected_name = "ppt12_demo_magnet_height_mm_listener"
    broker = dramatiq.get_broker()
    # Should not raise
    broker.get_actor(expected_name)


def test_status_readout_format_error_shows_inline_error(qapp):
    """When the format function raises, the label shows '<error: ...>'."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        status_readouts=[
            StatusReadout("Voltage", "v/applied", lambda m: f"{int(m)} V"),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    w._readout_signals["voltage"].emit("not-a-number")
    text = w._readout_labels["voltage"].text()
    assert text.startswith("Voltage: <error:")

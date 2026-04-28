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

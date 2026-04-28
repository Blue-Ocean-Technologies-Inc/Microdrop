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

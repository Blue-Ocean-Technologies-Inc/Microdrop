# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hardware-free tests for the portable heater temperature protocol
column."""

# Standard library imports.
import json
import threading

# Third-party imports.
import pytest

# Microdrop package imports.
import portable_dropbot_protocol_controls.protocol_columns.temperature_column as tc_mod
from pluggable_protocol_tree.execution.step_context import (
    ProtocolContext,
    StepContext,
)
from portable_dropbot_controller.consts import (
    DEFAULT_TEMP_CHANNEL,
    PROTOCOL_SET_TEMPERATURE,
    TEMP_CONTROL,
    TEMPERATURE_REACHED,
)
from portable_dropbot_protocol_controls.consts import SET_TEMPERATURE_FIELD_ID
from portable_dropbot_protocol_controls.plugin import (
    PortableDropbotProtocolControlsPlugin,
)
from portable_dropbot_protocol_controls.protocol_columns.temperature_column import (
    TemperatureCompoundModel,
    TemperatureHandler,
    TemperatureSetpointSpinBoxView,
    make_temperature_column,
)


class _Row:
    set_temperature = True
    target_temperature_c = 55.0
    tolerance_c = 1.5


class _Ctx:
    def __init__(self, preview=False):
        self.protocol = type("P", (), {"preview_mode": preview, "scratch": {}})()
        self.waited = None

    def wait_for(self, topic, timeout=None):
        self.waited = (topic, timeout)


def test_model_has_three_fields():
    specs = TemperatureCompoundModel().field_specs()
    assert [s.field_id for s in specs] == [
        SET_TEMPERATURE_FIELD_ID,
        "target_temperature_c",
        "tolerance_c",
    ]
    assert specs[0].default_value is False


def test_factory_and_plugin_contribution():
    col = make_temperature_column()
    assert col.handler.wait_for_topics == [TEMPERATURE_REACHED]
    assert col.handler.priority == 20
    cols = (
        PortableDropbotProtocolControlsPlugin()._contributed_protocol_columns_default()
    )
    assert any(c.model.base_id == "heater_temperature" for c in cols)


def test_on_step_publishes_and_waits(monkeypatch):
    pub = []
    monkeypatch.setattr(
        tc_mod, "publish_message", lambda topic, message: pub.append((topic, message))
    )
    handler = TemperatureHandler()
    handler.ack_time_s = 30.0
    ctx = _Ctx()
    handler.on_step(_Row(), ctx)

    topic, payload = pub[0]
    assert topic == PROTOCOL_SET_TEMPERATURE
    assert json.loads(payload) == {
        "channel": DEFAULT_TEMP_CHANNEL,
        "target_c": 55.0,
        "tolerance_c": 1.5,
    }
    assert ctx.waited == (TEMPERATURE_REACHED, 30.0)


def test_preview_mode_skips(monkeypatch):
    pub = []
    monkeypatch.setattr(
        tc_mod, "publish_message", lambda topic, message: pub.append((topic, message))
    )
    handler = TemperatureHandler()
    handler.ack_time_s = 30.0
    ctx = _Ctx(preview=True)
    handler.on_step(_Row(), ctx)
    assert pub == [] and ctx.waited is None


def test_zero_ack_publishes_without_waiting(monkeypatch):
    pub = []
    monkeypatch.setattr(
        tc_mod, "publish_message", lambda topic, message: pub.append((topic, message))
    )
    handler = TemperatureHandler()
    handler.ack_time_s = 0.0
    ctx = _Ctx()
    handler.on_step(_Row(), ctx)
    assert len(pub) == 1 and ctx.waited is None


def test_unchecked_step_leaves_heater_untouched(monkeypatch):
    """Set Temp off = no setpoint publish and no reached-ack wait."""
    pub = []
    monkeypatch.setattr(
        tc_mod, "publish_message", lambda topic, message: pub.append((topic, message))
    )
    handler = TemperatureHandler()
    handler.ack_time_s = 30.0

    class _UncheckedRow(_Row):
        set_temperature = False

    ctx = _Ctx()
    handler.on_step(_UncheckedRow(), ctx)
    assert pub == [] and ctx.waited is None


def test_setpoint_cells_read_only_until_checked():
    view = TemperatureSetpointSpinBoxView(low=0.0, high=150.0)

    class _UncheckedRow(_Row):
        set_temperature = False

    from pyface.qt.QtCore import Qt

    assert not (view.get_flags(_UncheckedRow()) & Qt.ItemIsEditable)
    assert view.get_flags(_Row()) & Qt.ItemIsEditable


def test_post_protocol_end_publishes_temp_control_off(monkeypatch):
    pub = []
    monkeypatch.setattr(
        tc_mod, "publish_message", lambda topic, message: pub.append((topic, message))
    )
    handler = TemperatureHandler()
    ctx = type("Ctx", (), {"preview_mode": False})()
    handler.on_post_protocol_end(ctx)

    assert len(pub) == 1
    topic, payload = pub[0]
    assert topic == TEMP_CONTROL
    assert json.loads(payload) == {"channel": DEFAULT_TEMP_CHANNEL, "on": False}


def test_post_protocol_end_skips_in_preview_mode(monkeypatch):
    pub = []
    monkeypatch.setattr(
        tc_mod, "publish_message", lambda topic, message: pub.append((topic, message))
    )
    handler = TemperatureHandler()
    ctx = type("Ctx", (), {"preview_mode": True})()
    handler.on_post_protocol_end(ctx)
    assert pub == []


# --------------------------------------------------------------------- #
# A failsafe alarm on the held loop fails the run at a step boundary     #
# --------------------------------------------------------------------- #


def _step_ctx(protocol):
    ctx = StepContext(row=None, protocol=protocol)
    ctx.open_mailbox(TEMPERATURE_REACHED)

    return ctx


@pytest.fixture
def protocol():
    return ProtocolContext(stop_event=threading.Event())


def _failure(error):
    return json.dumps({"channel": DEFAULT_TEMP_CHANNEL, "error": error})


def test_a_hold_phase_failure_fails_the_next_step_boundary(protocol, monkeypatch):
    monkeypatch.setattr(tc_mod, "publish_message", lambda topic, message: None)
    handler = TemperatureHandler()
    handler.ack_time_s = 0.0

    # A step drives the heater (fire-and-forget here, no ack wait)...
    handler.on_step(_Row(), _step_ctx(protocol))

    # ...and a later step's mailbox receives the backend's hold-phase error.
    later = _step_ctx(protocol)
    later.deposit(
        TEMPERATURE_REACHED, _failure("heater failsafe alarm 09001: over temp")
    )

    with pytest.raises(RuntimeError, match="09001"):
        handler.on_post_step(_Row(), later)


def test_step_boundaries_pass_without_a_failure(protocol, monkeypatch):
    monkeypatch.setattr(tc_mod, "publish_message", lambda topic, message: None)
    handler = TemperatureHandler()
    handler.ack_time_s = 0.0
    handler.on_step(_Row(), _step_ctx(protocol))
    ctx = _step_ctx(protocol)
    ctx.deposit(
        TEMPERATURE_REACHED,
        json.dumps({"channel": DEFAULT_TEMP_CHANNEL, "current_c": 55.0}),
    )

    handler.on_pre_step(_Row(), ctx)
    handler.on_post_step(_Row(), ctx)


def test_a_run_that_never_drove_the_heater_ignores_the_topic(protocol):
    handler = TemperatureHandler()
    ctx = _step_ctx(protocol)
    ctx.deposit(TEMPERATURE_REACHED, _failure("stale from another run"))

    handler.on_pre_step(_Row(), ctx)
    handler.on_post_step(_Row(), ctx)

"""Tests for the protocol-driven voltage/frequency setpoint handlers.

These handlers exist alongside the UI-driven on_set_voltage_request /
on_set_frequency_request but bypass the realtime-mode gate and skip
prefs persistence — protocol writes are unconditional and transient.
"""
from unittest.mock import MagicMock, patch

from dropbot_controller.consts import VOLTAGE_APPLIED
from dropbot_controller.services.dropbot_states_setting_mixin_service import (
    DropbotStatesSettingMixinService,
)


def _make_service():
    svc = DropbotStatesSettingMixinService()
    svc.proxy = MagicMock()  # MagicMock supports the transaction_lock context manager
    svc.preferences = MagicMock()
    return svc


def test_on_protocol_set_voltage_request_calls_proxy_and_publishes_ack():
    svc = _make_service()
    published = []
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        svc.on_protocol_set_voltage_request("100")

    svc.proxy.update_state.assert_called_once_with(voltage=100)
    assert published == [{"topic": VOLTAGE_APPLIED, "message": "100"}]


def test_on_protocol_set_voltage_request_bypasses_realtime_mode():
    """Unlike on_set_voltage_request, this handler runs even when realtime_mode is False."""
    svc = _make_service()
    svc.realtime_mode = False
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
    ):
        svc.on_protocol_set_voltage_request("75")

    svc.proxy.update_state.assert_called_once_with(voltage=75)


def test_on_protocol_set_voltage_request_does_not_persist_prefs():
    """Prefs are user-action-driven only; protocol writes don't churn them."""
    svc = _make_service()
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
    ):
        svc.on_protocol_set_voltage_request("90")

    setattr_calls = [
        c for c in svc.preferences.mock_calls
        if "last_voltage" in str(c)
    ]
    assert setattr_calls == []

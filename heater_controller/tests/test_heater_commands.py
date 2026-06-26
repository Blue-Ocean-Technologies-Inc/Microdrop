"""Hardware-free tests for the heater typed-command formatting.

Each typed request validates a JSON payload and formats the matching plain-text
command; these assert the wire strings without touching a serial port.
"""
import threading

import pytest

from heater_controller.heater_serial_proxy import HeaterSerialProxy
from heater_controller.services.heater_command_setter_service import HeaterCommandSetterService


class _Msg:
    """Stand-in for a TimestampedMessage (only .content is used)."""
    def __init__(self, content):
        self.content = content


def _make_service():
    """A command-setter wired to a fake proxy that records sent commands. The
    proxy is a real HeaterSerialProxy instance (so the Instance trait accepts it)
    built without opening a serial port."""
    proxy = HeaterSerialProxy.__new__(HeaterSerialProxy)
    proxy.transaction_lock = threading.Lock()
    proxy.sent = []
    proxy.send_command = lambda cmd: proxy.sent.append(cmd)
    return HeaterCommandSetterService(proxy=proxy)


@pytest.mark.parametrize("payload,expected", [
    ('{"heater": "tec1", "temperature": 40}', "pid_tec1_40.0"),
    ('{"temperature": 41.2}', "pid_tec1_41.2"),  # default heater
    ('{"heater": "tec2", "temperature": 37, "sensor_group": "top"}', "pid_tec2_37.0_top"),
])
def test_set_temperature(payload, expected):
    svc = _make_service()
    svc.on_set_temperature_request(_Msg(payload))
    assert svc.proxy.sent == [expected]


@pytest.mark.parametrize("payload,expected", [
    ('{"heater": "tec1", "pwm": 50}', "pwm_tec1_50"),
    ('{"pwm": 0}', "pwm_tec1_0"),  # default heater
])
def test_set_pwm(payload, expected):
    svc = _make_service()
    svc.on_set_pwm_request(_Msg(payload))
    assert svc.proxy.sent == [expected]


@pytest.mark.parametrize("mode", ["enable", "disable", "stop"])
def test_set_pid_mode(mode):
    svc = _make_service()
    svc.on_set_pid_mode_request(_Msg(f'{{"heater": "tec1", "mode": "{mode}"}}'))
    assert svc.proxy.sent == [f"pid_tec1_{mode}"]


@pytest.mark.parametrize("payload,expected", [
    ('{"group": "all"}', "stream_all"),
    ('{"group": "stop"}', "stream_stop"),
    ('{"group": "top"}', "stream_top"),
    ('{}', "stream_all"),  # default group
])
def test_set_stream(payload, expected):
    svc = _make_service()
    svc.on_set_stream_request(_Msg(payload))
    assert svc.proxy.sent == [expected]


@pytest.mark.parametrize("payload,expected", [
    ('{"on": true}', "fan_on"),
    ('{"on": false}', "fan_off"),
])
def test_set_fan(payload, expected):
    svc = _make_service()
    svc.on_set_fan_request(_Msg(payload))
    assert svc.proxy.sent == [expected]


def test_all_off_ignores_payload():
    svc = _make_service()
    svc.on_all_off_request(_Msg(""))
    assert svc.proxy.sent == ["all_off"]


def test_generic_send_command_passthrough():
    svc = _make_service()
    svc.on_send_command_request(_Msg("whoami"))
    assert svc.proxy.sent == ["whoami"]


def test_empty_generic_command_ignored():
    svc = _make_service()
    svc.on_send_command_request(_Msg(""))
    assert svc.proxy.sent == []


@pytest.mark.parametrize("handler,payload", [
    ("on_set_pwm_request", '{"pwm": 200}'),          # out of 0-100 range
    ("on_set_pid_mode_request", '{"mode": "boost"}'),  # not a valid mode
    ("on_set_temperature_request", '{"heater": "tec1"}'),  # missing temperature
    ("on_set_pwm_request", 'not json'),
])
def test_invalid_payloads_send_nothing(handler, payload):
    svc = _make_service()
    getattr(svc, handler)(_Msg(payload))
    assert svc.proxy.sent == []

"""Hardware-free tests for the protocol set-temperature watch + handler."""
import json
import threading

import heater_controller.heater_serial_proxy as proxy_mod
from heater_controller.heater_serial_proxy import HeaterSerialProxy
from heater_controller.services.heater_command_setter_service import HeaterCommandSetterService
from heater_controller.consts import TEMPERATURE_REACHED


class _Msg:
    def __init__(self, content):
        self.content = content


def _proxy():
    p = HeaterSerialProxy.__new__(HeaterSerialProxy)   # no serial port opened
    p._temp_watch = None
    return p


def test_watch_acks_only_within_tolerance_for_the_right_heater(monkeypatch):
    pub = []
    monkeypatch.setattr(proxy_mod, "publish_message",
                        lambda message, topic, **k: pub.append((topic, message)))
    p = _proxy()
    p.set_temperature_target("tec1", 50.0, 1.0)

    p._check_temperature_watch("PID_TEC2", {"pid_temperature": 50.0})  # wrong heater
    p._check_temperature_watch("PID_TEC1", {"pid_temperature": 45.0})  # out of band
    assert pub == [] and p._temp_watch is not None

    p._check_temperature_watch("PID_TEC1", {"pid_temperature": 49.4})  # within band
    assert p._temp_watch is None                                       # disarmed
    topic, payload = pub[-1]
    assert topic == TEMPERATURE_REACHED
    assert json.loads(payload) == {"heater": "tec1", "temperature": 49.4}


def test_watch_disarms_after_ack(monkeypatch):
    pub = []
    monkeypatch.setattr(proxy_mod, "publish_message",
                        lambda message, topic, **k: pub.append((topic, message)))
    p = _proxy()
    p.set_temperature_target("tec1", 50.0, 1.0)
    p._check_temperature_watch("PID_TEC1", {"pid_temperature": 50.0})
    pub.clear()
    p._check_temperature_watch("PID_TEC1", {"pid_temperature": 50.0})  # already reached
    assert pub == []


class _FakeProxy(HeaterSerialProxy):
    def __init__(self, available_heaters=()):
        self.transaction_lock = threading.Lock()
        self.available_heaters = list(available_heaters)
        self.sent = []
        self.armed = None

    def send_command(self, cmd):
        self.sent.append(cmd)

    def set_temperature_target(self, heater, target, tolerance):
        self.armed = (heater, target, tolerance)


def _run_protocol_set(proxy, heater="tec1"):
    service = HeaterCommandSetterService()
    service.proxy = proxy
    service.on_protocol_set_temperature_request(
        _Msg(json.dumps({"heater": heater, "temperature": 60, "tolerance": 2})))
    return proxy


def test_protocol_handler_sets_target_and_arms_watch():
    proxy = _run_protocol_set(_FakeProxy())   # no available list -> heater unchanged
    assert "pid_tec1_enable" in proxy.sent
    assert "pid_tec1_60.0" in proxy.sent
    assert "stream_all" in proxy.sent          # ensure telemetry flows
    assert proxy.armed == ("tec1", 60.0, 2.0)


def test_protocol_handler_resolves_default_heater_to_real_channel():
    # The board reports "heater1"; the protocol's default "tec1" must be remapped
    # so both the PID command and the watch target the real channel.
    proxy = _run_protocol_set(_FakeProxy(available_heaters=["heater1"]), heater="tec1")
    assert "pid_heater1_enable" in proxy.sent
    assert "pid_heater1_60.0" in proxy.sent
    assert proxy.armed == ("heater1", 60.0, 2.0)


def test_watch_matches_resolved_heater_frame(monkeypatch):
    # Regression: watch armed for "heater1" must match a PID_HEATER1 frame.
    pub = []
    monkeypatch.setattr(proxy_mod, "publish_message",
                        lambda message, topic, **k: pub.append((topic, message)))
    p = _proxy()
    p.set_temperature_target("heater1", 50.0, 1.0)
    p._check_temperature_watch("PID_HEATER1", {"pid_temperature": 50.2})
    assert pub and pub[-1][0] == TEMPERATURE_REACHED
    assert p._temp_watch is None

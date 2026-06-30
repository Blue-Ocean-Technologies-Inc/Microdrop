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


def test_protocol_handler_sets_target_and_arms_watch():
    class FakeProxy(HeaterSerialProxy):
        def __init__(self):
            self.transaction_lock = threading.Lock()
            self.sent = []
            self.armed = None

        def send_command(self, cmd):
            self.sent.append(cmd)

        def set_temperature_target(self, heater, target, tolerance):
            self.armed = (heater, target, tolerance)

    service = HeaterCommandSetterService()
    service.proxy = FakeProxy()
    service.on_protocol_set_temperature_request(
        _Msg(json.dumps({"heater": "tec1", "temperature": 60, "tolerance": 2})))

    assert "pid_tec1_enable" in service.proxy.sent
    assert "pid_tec1_60.0" in service.proxy.sent
    assert "stream_all" in service.proxy.sent         # ensure telemetry flows
    assert service.proxy.armed == ("tec1", 60.0, 2.0)

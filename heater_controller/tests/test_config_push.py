"""Hardware-free tests for the save-config-to-board push orchestration.

mpremote, the serial proxy, and message publishing are all stubbed, so this
exercises only the ordering: validate payload -> release the port -> run
mpremote -> always reconnect -> publish the result.
"""
import json
import threading

import pytest

import heater_controller.services.heater_config_service as svc_mod
from heater_controller.services.heater_config_service import HeaterConfigService
from heater_controller.heater_serial_proxy import HeaterSerialProxy
from heater_controller.consts import CONFIG_PUSHED, DISCONNECTED


CONFIG = {"heaters": {"t": {"type": "tec", "sensors": ["s"]}},
          "temperature_sensors": {"1-wire-sensors": {"s": "28aa"}}}


class _FakeProxy(HeaterSerialProxy):
    """A HeaterSerialProxy that never opens a port (so Instance(...) accepts it)."""
    def __init__(self):
        self.port = "COM7"
        self.terminated = False
        self.transaction_lock = threading.Lock()

    def terminate(self):
        self.terminated = True


class _Msg:
    def __init__(self, content):
        self.content = content


@pytest.fixture
def published(monkeypatch):
    sink = []
    monkeypatch.setattr(svc_mod, "publish_message",
                        lambda message, topic=None, **k: sink.append((topic, message)))
    return sink


def _service(mpremote_raises=None):
    service = HeaterConfigService()
    service.proxy = _FakeProxy()
    service.disconnected_topic = DISCONNECTED   # supplied by the composed base
    calls = []

    def fake_mpremote(port, *args):
        calls.append(args[0])
        if mpremote_raises:
            raise RuntimeError(mpremote_raises)

    service._mpremote = fake_mpremote
    return service, calls


def _result(published):
    return json.loads(dict(published)[CONFIG_PUSHED])


def test_push_success_releases_port_copies_resets_and_reconnects(published):
    service, calls = _service()
    proxy = service.proxy
    service.on_save_config_to_board_request(_Msg(json.dumps(CONFIG)))

    assert proxy.terminated and service.proxy is None       # serial port released
    assert calls == ["cp", "reset"]                          # copy then reboot
    assert DISCONNECTED in [t for t, _ in published]         # reconnect triggered
    assert _result(published)["ok"] is True


def test_push_failure_still_reconnects_and_reports_error(published):
    service, _ = _service(mpremote_raises="boom")
    service.on_save_config_to_board_request(_Msg(json.dumps(CONFIG)))

    assert DISCONNECTED in [t for t, _ in published]         # reconnect regardless
    result = _result(published)
    assert result["ok"] is False and "boom" in result["message"]


def test_push_invalid_payload_leaves_connection_untouched(published):
    service, calls = _service()
    proxy = service.proxy
    service.on_save_config_to_board_request(_Msg("not json"))

    assert not proxy.terminated and service.proxy is proxy   # nothing released
    assert calls == []
    assert _result(published)["ok"] is False

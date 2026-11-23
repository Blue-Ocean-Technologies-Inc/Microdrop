# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater requests are held to what MCU 1.0.1.31 accepts (2 loops, gains
0..100, not Kp = Ki = 0, targets below max_temp_c - 5), and a heater
failsafe alarm fails the protocol step waiting on its loop. Hardware-free,
no Redis."""

# Standard library imports.
import json
import struct
import threading
import time

# Third-party imports.
import pytest
from dropbot_portable.proxy import SignalBoardProxy
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Any, HasTraits

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    AlarmRaised,
    TemperatureReached,
    TempSetPidRequest,
    TempSetTargetRequest,
)
from portable_dropbot_controller.heater_limits import (
    heater_failsafe_alarms,
    heater_target_refusal,
)
from portable_dropbot_controller.services import (
    portable_dropbot_temp_mixin_service as temp_service,
)

VALID_PID = {"channel": 1, "kp": 10.0, "ki": 0.5, "kd": 0.0, "period_ms": 1000}


def test_a_valid_pid_set_passes():
    assert TempSetPidRequest.model_validate(VALID_PID).kp == 10.0


@pytest.mark.parametrize(
    "change",
    [
        {"kp": 100.5},
        {"ki": -1.0},
        {"kd": 101.0},
        {"channel": 2},
        {"period_ms": 0},
        {"period_ms": 65_536},
    ],
)
def test_out_of_range_pid_values_are_refused(change):
    with pytest.raises(ValidationError):
        TempSetPidRequest.model_validate({**VALID_PID, **change})


@pytest.mark.parametrize("kp, ki", [(0.0, 0.0), (0.004, 0.0049)])
def test_kp_and_ki_both_zero_on_the_wire_is_refused(kp, ki):
    with pytest.raises(ValidationError, match="Kp and Ki cannot both be 0"):
        TempSetPidRequest.model_validate({**VALID_PID, "kp": kp, "ki": ki})


def test_a_gain_that_rounds_up_to_001_drives_the_loop():
    TempSetPidRequest.model_validate({**VALID_PID, "kp": 0.0, "ki": 0.006})


def test_the_period_reaches_the_uint16_ceiling():
    request = {**VALID_PID, "period_ms": 65_535}

    assert TempSetPidRequest.model_validate(request).period_ms == 65_535


def test_only_the_two_heater_loops_take_a_target():
    TempSetTargetRequest(channel=1, target_c=60.0)

    with pytest.raises(ValidationError):
        TempSetTargetRequest(channel=3, target_c=60.0)


@pytest.mark.parametrize(
    "target_c, max_temp_c, refused",
    [(114.99, 120, False), (115.0, 120, True), (140.0, 150, False), (36.0, 40, True)],
)
def test_targets_stay_below_the_max_temperature_minus_5(target_c, max_temp_c, refused):
    assert bool(heater_target_refusal(target_c, max_temp_c)) == refused


def _alarm(**report):
    return AlarmRaised(command="0x12FF", reports=[report])


def test_failsafe_alarms_name_their_loop():
    alarm = _alarm(
        text="[09002] Heater may be disconnected",
        code="09002",
        detail="htr1 no temp rise at full power",
        active=1,
    )

    [(code, channel, _text)] = heater_failsafe_alarms(alarm)

    assert (code, channel) == ("09002", 1)


def test_clears_and_other_alarms_are_skipped():
    cleared = _alarm(text="[09004] Host silent", code="09004", active=0)
    other = _alarm(text="[05003] Temperature sensor", code="05003", active=1)

    assert heater_failsafe_alarms(cleared) == []
    assert heater_failsafe_alarms(other) == []


def test_legacy_display_strings_are_read_too():
    alarm = AlarmRaised(command="0x12FF", alarms=["[09004] Host silent"])

    assert heater_failsafe_alarms(alarm) == [("09004", None, "[09004] Host silent")]


# --------------------------------------------------------------------- #
# The temp mixin fails a waiting protocol step                           #
# --------------------------------------------------------------------- #


class _Publisher:
    def __init__(self):
        self.published = []

    def publish(self, payload):
        self.published.append(TemperatureReached.model_validate(payload))


class _Uart:
    def __init__(self, max_temp_c=120):
        self.max_temp_c = max_temp_c
        self.targets = []

    def heater_failsafe(self):
        return 300, 5, self.max_temp_c

    def set_temp_target(self, target_c, channel):
        self.targets.append((channel, target_c))

        return True

    def set_temp_control(self, on, channel):
        return True


class _Base(HasTraits):
    proxy = Any()
    errors = Any()

    def _proxy_call(self, context, call):
        return True, call()

    def _publish_error(self, context, error):
        self.errors.append((context, error))


class _Harness(temp_service.PortableDropbotTempMixinService, _Base):
    pass


@pytest.fixture
def published(monkeypatch):
    publisher = _Publisher()
    monkeypatch.setattr(temp_service, "temperature_reached_publisher", publisher)

    return publisher.published


@pytest.fixture
def harness():
    h = _Harness(errors=[])
    h.proxy = type("Session", (), {"uart": _Uart()})()

    return h


def test_a_refused_protocol_setpoint_fails_the_step_at_once(harness, published):
    harness.on_protocol_set_temperature_request(
        json.dumps({"channel": 0, "target_c": 118.0, "tolerance_c": 1.0})
    )

    assert harness.proxy.uart.targets == []
    assert "118" in published[0].error


def test_a_refused_pane_target_is_not_sent(harness):
    harness.on_temp_set_target_request(json.dumps({"channel": 0, "target_c": 116.0}))

    assert harness.proxy.uart.targets == []
    assert "below 115" in harness.errors[0][1]


def test_a_failsafe_alarm_fails_the_waiting_step(harness, published):
    harness._temp_reached_cancel = threading.Event()
    harness._temp_reached_channel = 0
    alarm = _alarm(
        text="[09001] Heater over temperature",
        code="09001",
        detail="htr0 S1 above max",
        active=1,
    )

    harness.on_alarm_signal(alarm.model_dump_json())

    assert harness._temp_reached_cancel.is_set()
    assert published[0].channel == 0
    assert "09001" in published[0].error


def test_an_alarm_for_the_other_loop_is_ignored(harness, published):
    harness._temp_reached_cancel = threading.Event()
    harness._temp_reached_channel = 0
    alarm = _alarm(text="[09002] x", code="09002", detail="htr1 no rise", active=1)

    harness.on_alarm_signal(alarm.model_dump_json())

    assert not harness._temp_reached_cancel.is_set()
    assert published == []


# --------------------------------------------------------------------- #
# The hold phase: an alarm after the reached ack still fails the run     #
# --------------------------------------------------------------------- #


class _ReadingUart(_Uart):
    """Reads the target back at once, so the watcher acks on its first poll."""

    def get_temp_info(self, channel):
        _channel, target_c = self.targets[-1]

        return target_c, target_c, 10.0


def _wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout

    while not condition():
        assert time.monotonic() < deadline, "condition never became true"
        time.sleep(0.01)


@pytest.fixture
def holding_harness(monkeypatch, harness):
    monkeypatch.setattr(temp_service, "TEMP_REACHED_POLL_INTERVAL_S", 0.02)
    monkeypatch.setattr(temp_service, "publish_message", lambda **kwargs: None)
    harness.proxy.uart = _ReadingUart()

    yield harness

    harness._cancel_temp_reached_watcher()


def _overheat_alarm():
    return _alarm(
        text="[09001] Heater over temperature",
        code="09001",
        detail="htr0 S1 above max",
        active=1,
    ).model_dump_json()


def test_a_hold_phase_alarm_fails_the_protocol_until_heater_off(
    holding_harness, published
):
    holding_harness.on_protocol_set_temperature_request(
        json.dumps({"channel": 0, "target_c": 60.0, "tolerance_c": 1.0})
    )
    _wait_until(lambda: published and published[0].current_c == 60.0)

    # The step has its ack; the loop is still held.
    assert holding_harness._temp_holding.is_set()
    assert not holding_harness._temp_reached_cancel.is_set()

    holding_harness.on_alarm_signal(_overheat_alarm())

    errors = [p for p in published if p.error]
    assert errors and "09001" in errors[0].error
    assert "holding" in errors[0].error

    # Republished every poll, so a step boundary after a pause still sees it.
    _wait_until(lambda: len([p for p in published if p.error]) >= 3)

    # The run's heater-off ends the hold and the republishing.
    holding_harness.on_temp_control_request(json.dumps({"channel": 0, "on": False}))
    holding_harness._temp_reached_watcher.join(timeout=5)
    count = len(published)
    time.sleep(0.1)

    assert len(published) == count


def test_heater_off_for_the_other_loop_keeps_the_hold(holding_harness, published):
    holding_harness.on_protocol_set_temperature_request(
        json.dumps({"channel": 0, "target_c": 60.0, "tolerance_c": 1.0})
    )
    _wait_until(lambda: holding_harness._temp_holding.is_set())

    holding_harness.on_temp_control_request(json.dumps({"channel": 1, "on": False}))

    assert not holding_harness._temp_reached_cancel.is_set()


# --------------------------------------------------------------------- #
# PID set / read go through the generated proxy (uint16, rounded)        #
# --------------------------------------------------------------------- #


class _Transport:
    """What the generated SignalBoardProxy needs from the uart: the sent
    payloads, and a canned reply."""

    def __init__(self, reply=b""):
        self.reply = reply
        self.sent = []

    def _make_cmd_packet(self, cmd, payload):
        return payload

    def _wr(self, packet, cmd, timeout_s):
        self.sent.append((cmd, packet))

        return self.reply


@pytest.fixture
def pid_published(monkeypatch):
    messages = []
    monkeypatch.setattr(
        temp_service,
        "publish_message",
        lambda topic, message: messages.append(json.loads(message)),
    )

    return messages


def _pid_harness(transport):
    harness = _Harness(errors=[])
    harness.proxy = type("Session", (), {"sig": SignalBoardProxy(transport)})()

    return harness


def test_a_pid_set_packs_uint16_and_rounds_the_gains(pid_published):
    transport = _Transport(reply=b"\x00")
    harness = _pid_harness(transport)

    harness.on_temp_set_pid_request(
        json.dumps({**VALID_PID, "kp": 0.29, "period_ms": 40_000})
    )

    [(_cmd, payload)] = transport.sent

    assert struct.unpack(">BHHHH", payload) == (1, 29, 50, 0, 40_000)
    assert pid_published == [{"channel": 1, "pid_applied": True, "pid_error": ""}]


def test_a_pid_read_decodes_a_period_above_32767(pid_published):
    transport = _Transport(reply=struct.pack(">BHHHH", 0, 29, 50, 0, 40_000))
    harness = _pid_harness(transport)

    harness.on_temp_read_pid_request("0")

    assert pid_published == [
        {
            "channel": 0,
            "pid": {
                "channel": 0,
                "kp": 0.29,
                "ki": 0.5,
                "kd": 0.0,
                "period_ms": 40_000,
            },
        }
    ]

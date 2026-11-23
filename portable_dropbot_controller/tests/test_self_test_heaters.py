# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test heat step's heaters: registered while the heater test runs
and switched off by a disconnect or teardown meanwhile, as the vendor
worker's ``shutdown_heaters``. Hardware-free, no Redis."""

# Standard library imports.
import struct
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, Int, List

# Microdrop package imports.
from portable_dropbot_controller import self_test_board
from portable_dropbot_controller.self_test_board import SelfTestBoard, heaters_driven
from portable_dropbot_controller.services import (
    portable_dropbot_self_test_state_mixin_service as state_mod,
)
from portable_dropbot_controller.session_shutdown import switch_heaters_off

#: TEMP_START_STOP's signal-board command id.
TEMP_START_STOP = 0x1211


class _Uart:
    """Records every request the generated proxy sends through it."""

    def __init__(self, sig_board_connected=True):
        self.sig_board_connected = sig_board_connected
        self.sent = []
        self.waits = []

    def _make_cmd_packet(self, cmd, payload):
        return (cmd, payload)

    def _w(self, data):
        return True

    def _wr(self, packet, cmd, timeout_s=1.0, min_len=0, lock_timeout_s=None):
        self.sent.append(packet)
        self.waits.append((timeout_s, lock_timeout_s))

        return b"\x01"


def test_switch_heaters_off_stops_each_loop_bounded():
    uart = _Uart()

    steps = switch_heaters_off(SimpleNamespace(uart=uart), [0, 1], timeout_s=0.5)

    assert uart.sent == [
        (TEMP_START_STOP, struct.pack(">BB", 0, 0)),
        (TEMP_START_STOP, struct.pack(">BB", 1, 0)),
    ]
    assert steps == ["temp_start_stop(0, 0) -> OK", "temp_start_stop(1, 0) -> OK"]
    assert all(wait <= 0.5 and lock <= 0.2 for wait, lock in uart.waits)


def test_switch_heaters_off_sends_nothing_without_the_signal_board():
    uart = _Uart(sig_board_connected=False)

    assert switch_heaters_off(SimpleNamespace(uart=uart), [0, 1]) == []
    assert uart.sent == []


def test_only_the_heat_step_drives_the_heaters():
    assert heaters_driven("test_heaters", {}) == [0, 1]
    assert heaters_driven("test_heaters", {"heat_step": True}) == [0, 1]
    assert heaters_driven("test_heaters", {"heat_step": False}) == []
    assert heaters_driven("test_motors", {"moves": True}) == []


# --------------------------------------------------------------------- #
# Registration around the heater test                                   #
# --------------------------------------------------------------------- #


class _Controller(state_mod.PortableDropbotSelfTestStateMixinService):
    """The state mixin plus the controller members the hub uses."""

    proxy = Any()
    portable_dropbot_connection_active = Bool(True)
    #: The registered heaters each proxy call saw.
    heaters_seen = List()
    raise_in_call = Bool(False)
    calls = Int(0)

    def _proxy_call(self, context, call, serialize=True):
        self.heaters_seen.append(list(self._self_test_heaters))
        self.calls += 1

        if self.raise_in_call:
            raise RuntimeError("driver blew up")

        return True, call()


@pytest.fixture
def silent_publishers(monkeypatch):
    published = []
    recorder = SimpleNamespace(publish=published.append)
    monkeypatch.setattr(self_test_board, "self_test_result_publisher", recorder)
    monkeypatch.setattr(self_test_board, "self_test_progress_publisher", recorder)

    return published


def _board(controller, test_kwargs):
    return SelfTestBoard(
        controller=controller,
        bot=object(),
        run_id="r",
        tests=["test_heaters"],
        test_kwargs=test_kwargs,
    )


def _step(name="test_heaters"):
    return SimpleNamespace(test=name, index=0)


def test_the_heater_test_registers_its_heaters_for_its_duration(
    monkeypatch, silent_publishers
):
    monkeypatch.setattr(
        self_test_board, "self_test", lambda bot, tests, **kw: {tests[0]: {"ok": 1}}
    )
    controller = _Controller()

    _board(controller, {"test_heaters": {"heat_step": True}}).run_test(_step())

    assert controller.heaters_seen == [[0, 1]]
    assert controller._self_test_heaters == []


def test_a_failing_heater_test_still_unregisters(monkeypatch, silent_publishers):
    controller = _Controller(raise_in_call=True)

    with pytest.raises(RuntimeError):
        _board(controller, {}).run_test(_step())

    assert controller.heaters_seen == [[0, 1]]
    assert controller._self_test_heaters == []


# --------------------------------------------------------------------- #
# Disconnect and teardown                                               #
# --------------------------------------------------------------------- #


@pytest.fixture
def heaters_off(monkeypatch):
    sent = []

    def record(session, channels):
        sent.append((session, list(channels)))

        return [f"temp_start_stop({channel}, 0) -> OK" for channel in channels]

    monkeypatch.setattr(state_mod, "switch_heaters_off", record)

    return sent


def test_a_disconnect_mid_heat_step_switches_the_heaters_off(heaters_off):
    session = object()
    controller = _Controller(proxy=session, _self_test_heaters=[0, 1])

    controller.portable_dropbot_connection_active = False

    assert heaters_off == [(session, [0, 1])]


def test_a_disconnect_without_a_heat_step_leaves_the_heaters_alone(heaters_off):
    controller = _Controller(proxy=object())

    controller.portable_dropbot_connection_active = False

    assert heaters_off == []


def test_teardown_switch_off_needs_a_session(heaters_off):
    controller = _Controller(proxy=None, _self_test_heaters=[0])

    controller._switch_off_self_test_heaters("self-test teardown")

    assert heaters_off == []

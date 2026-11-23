# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""HV across a disconnect: a deliberate close (user Disconnect, firmware
update yield) switches HV off, clears the electrodes and powers the PMT off
first, every link that ends ends realtime mode, and a connect never
re-enables HV on its own. Hardware-free, no Redis: the generated proxy runs
over a recording fake transport."""

# Standard library imports.
import os
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Int, List

# Microdrop package imports.
from portable_dropbot_controller.consts import SHUTDOWN_TIMEOUT_S
from portable_dropbot_controller.port_lease_guard import PortLeaseGuard
from portable_dropbot_controller.services import (
    portable_dropbot_monitor_mixin_service as mod,
)
from portable_dropbot_controller.session_shutdown import deenergize_session

#: Signal board command ids the de-energize sends.
HV_ENABLE, ELECTRODE_STATE_CH, PMT_POWER = 0x1234, 0x1242, 0x122B

FLASH = {"owner": "flash", "pid": os.getpid() + 1, "phase": "streaming"}


class _Uart:
    """Records every request the generated proxy sends through it."""

    def __init__(self, log, sig_board_connected=True, board_channels=200):
        self.log = log
        self.sig_board_connected = sig_board_connected
        self.board_channels = board_channels
        self.waits = []
        self.raise_on = None

    def _make_cmd_packet(self, cmd, payload):
        return (cmd, payload)

    def _w(self, data):
        return True

    def _wr(self, packet, cmd, timeout_s=1.0, min_len=0, lock_timeout_s=None):
        self.waits.append((timeout_s, lock_timeout_s))

        if cmd == self.raise_on:
            raise OSError("write failed")

        self.log.append(packet)

        # hv_enable answers HV off (1); the others a one-byte OK.
        return b"\x01"


class _Session:
    def __init__(self, log, **uart_kwargs):
        self.log = log
        self.uart = _Uart(log, **uart_kwargs)

    def disconnect(self):
        self.log.append("disconnect")


def _sent(log):
    return [entry for entry in log if entry != "disconnect"]


# --------------------------------------------------------------------- #
# deenergize_session                                                     #
# --------------------------------------------------------------------- #


def test_deenergize_switches_hv_off_clears_electrodes_and_powers_pmt_off():
    log = []
    session = _Session(log)

    steps = deenergize_session(session)

    assert log == [
        (HV_ENABLE, b"\x00\x00"),
        (ELECTRODE_STATE_CH, bytes(25)),
        (PMT_POWER, b"\x00"),
    ]
    assert len(steps) == 3 and all(step.endswith("OK") for step in steps)
    assert all(
        timeout <= SHUTDOWN_TIMEOUT_S and lock <= 0.2
        for timeout, lock in session.uart.waits
    )


def test_deenergize_keeps_going_past_a_failing_command():
    log = []
    session = _Session(log)
    session.uart.raise_on = HV_ENABLE

    steps = deenergize_session(session)

    assert "FAILED" in steps[0]
    assert [cmd for cmd, _payload in log] == [ELECTRODE_STATE_CH, PMT_POWER]


def test_deenergize_sends_nothing_without_the_signal_board():
    log = []

    assert deenergize_session(_Session(log, sig_board_connected=False)) == []
    assert deenergize_session(SimpleNamespace()) == []
    assert log == []


# --------------------------------------------------------------------- #
# The monitor's disconnect paths                                         #
# --------------------------------------------------------------------- #


class _FakeLease:
    def __init__(self):
        self.holders = {}

    def holder(self, port):
        return self.holders.get(port)

    def acquire_use(self, port):
        return SimpleNamespace(release=lambda: None)


class _Base(HasTraits):
    proxy = Any()
    preferences = Any()
    errors = List()
    realtime_mode = Bool(False)
    realtime_published = List()
    voltage = Int()
    frequency = Int()
    light_intensity = Int()

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")

    def _publish_realtime_mode(self):
        self.realtime_published.append(self.realtime_mode)

    def _publish_disconnected(self):
        pass

    def _publish_connected(self):
        pass

    def _publish_status_snapshot(self):
        pass

    def _publish_alarm(self, cmd, alarms):
        pass

    def _apply_actuation(self):
        pass

    def _apply_light_intensity(self):
        pass


class _Harness(mod.PortableDropbotMonitorMixinService, _Base):
    pass


@pytest.fixture
def lease():
    return _FakeLease()


@pytest.fixture
def harness(lease):
    guard = PortLeaseGuard(
        lease_holder=lease.holder, acquire_use=lease.acquire_use, clock=lambda: 0.0
    )

    return _Harness(port_lease_guard=guard)


def _connected(harness, log):
    harness.proxy = _Session(log)
    harness.portable_dropbot_connection_active = True
    harness._connected_port = "COM5"
    harness.realtime_mode = True


def test_user_disconnect_deenergizes_before_closing_and_ends_realtime(harness):
    log = []
    _connected(harness, log)

    harness.on_disconnect_request("")

    assert log[0] == (HV_ENABLE, b"\x00\x00")
    assert log[-1] == "disconnect"
    assert (PMT_POWER, b"\x00") in log
    assert harness.proxy is None
    assert harness.realtime_mode is False
    assert harness.realtime_published == [False]


def test_firmware_update_yield_deenergizes_before_closing(harness, lease):
    log = []
    _connected(harness, log)
    lease.holders["COM5"] = FLASH

    harness._monitor_tick()

    assert log[0] == (HV_ENABLE, b"\x00\x00")
    assert log[-1] == "disconnect"
    assert harness.realtime_mode is False
    assert harness.realtime_published == [False]


def test_a_lost_link_closes_without_deenergize_but_still_ends_realtime(harness):
    log = []
    _connected(harness, log)

    harness.on_disconnected_signal("")

    assert log == ["disconnect"]
    assert harness.realtime_mode is False


class _ConnectingSession:
    """DropBotSession stand-in for _attempt_connect."""

    instances = []

    def __init__(self):
        self.log = []
        self.uart = SimpleNamespace(
            motor_board_connected=True, sig_board_connected=True, on_alarm=None
        )
        self.sig = SimpleNamespace(
            hv_enable=lambda enable, bypass: self.log.append(("hv", enable, bypass))
        )
        _ConnectingSession.instances.append(self)

    def connect(self, port, baudrate, autodetect):
        return True

    @property
    def connected(self):
        return True

    def check_versions(self, ignore=False):
        return {}

    def disconnect(self):
        pass


def test_a_connect_never_reenables_hv_on_its_own(harness, monkeypatch):
    _ConnectingSession.instances = []
    monkeypatch.setattr(mod, "DropBotSession", _ConnectingSession)
    monkeypatch.setattr(mod.firmware_versions_publisher, "publish", lambda p: None)
    harness.preferences = SimpleNamespace(
        baud_rate=115200,
        default_voltage=100,
        default_frequency=10_000,
        default_light_intensity=50,
        port_hint="",
    )
    # A realtime left on by a path that skipped the reset.
    harness.realtime_mode = True

    assert harness._attempt_connect("COM5") is True

    [session] = _ConnectingSession.instances
    assert session.log == [("hv", 0, 0)]
    assert harness.realtime_mode is False
    assert harness.realtime_published == [False]

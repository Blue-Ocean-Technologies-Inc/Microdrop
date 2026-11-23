# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Bounded connect (#1065): a driver connect stuck in a serial write is
abandoned after its deadline or on cleanup, its port is unblocked and closed
in the background, a good connect is unaffected, and the scan never offers
Bluetooth ports. Fake sessions only: no hardware, no driver internals."""

# Standard library imports.
import threading
import time
from types import SimpleNamespace

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, Int, List, Str

# Microdrop package imports.
from portable_dropbot_controller import connect_attempt
from portable_dropbot_controller.connect_attempt import (
    ConnectAttempt,
    ConnectAttemptCancelled,
    ConnectAttemptTimeout,
)
from portable_dropbot_controller.services import (
    portable_dropbot_monitor_mixin_service as mod,
)


class _StuckPort:
    """A pyserial port whose write never drains until cancel_write."""

    def __init__(self):
        self.is_open = True
        self.write_timeout = None
        self.cancelled = threading.Event()

    def cancel_write(self):
        self.cancelled.set()


class _StuckSession:
    """connect() blocks like the driver's login write on a dead port."""

    instances = []

    def __init__(self):
        self.uart = SimpleNamespace(serial=_StuckPort())
        self.disconnected = threading.Event()
        _StuckSession.instances.append(self)

    def connect(self, **kwargs):
        self.uart.serial.cancelled.wait()

        raise OSError("Write timeout")

    def disconnect(self):
        self.disconnected.set()


class _GoodSession:
    """A board that answers both logins at once."""

    instances = []

    def __init__(self):
        self.uart = SimpleNamespace(
            serial=None,
            motor_board_connected=True,
            sig_board_connected=True,
            on_alarm=None,
        )
        self.sig = SimpleNamespace(hv_enable=lambda *args: None)
        self.connected = True
        self.connect_kwargs = None
        self.disconnected = threading.Event()
        _GoodSession.instances.append(self)

    def connect(self, **kwargs):
        self.connect_kwargs = kwargs

        return True

    def check_versions(self, ignore=False):
        return {}

    def disconnect(self):
        self.disconnected.set()


class _Preferences(HasTraits):
    port_hint = Str()
    baud_rate = Int(115200)
    default_voltage = Int(100)
    default_frequency = Int(10000)
    default_light_intensity = Int(0)


class _Base(HasTraits):
    proxy = Any()
    preferences = Any()
    voltage = Int()
    frequency = Int()
    light_intensity = Int()
    realtime_mode = Bool(False)
    errors = List()
    connected_published = Bool(False)
    cleaned_up = Bool(False)

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")

    def _publish_alarm(self, cmd, alarms):
        pass

    def _publish_connected(self):
        self.connected_published = True

    def _publish_status_snapshot(self):
        pass

    def _apply_actuation(self):
        pass

    def _apply_light_intensity(self):
        pass

    def cleanup(self):
        self.cleaned_up = True


class _Harness(mod.PortableDropbotMonitorMixinService, _Base):
    pass


def _harness():
    return _Harness(preferences=_Preferences())


def _wait_until(predicate, timeout_s=2.0):
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        if predicate():
            return True

        time.sleep(0.01)

    return predicate()


def _connect_threads():
    """Live worker and release threads of connect attempts."""
    return [
        thread
        for thread in threading.enumerate()
        if thread.name.startswith("portable-connect") and thread.is_alive()
    ]


# --------------------------------------------------------------------------- #
# ConnectAttempt                                                               #
# --------------------------------------------------------------------------- #


def test_blocked_connect_is_abandoned_after_the_deadline():
    session = _StuckSession()
    attempt = ConnectAttempt(session=session, port_name="COM4")

    started = time.monotonic()
    connected = attempt.run(0.2)
    elapsed = time.monotonic() - started

    assert connected is False
    assert elapsed < 1.0
    assert attempt.abandoned is True
    assert isinstance(attempt.error, ConnectAttemptTimeout)

    # The release thread unblocks the write first, then closes the port.
    assert session.uart.serial.cancelled.wait(2)
    assert session.uart.serial.write_timeout is not None
    assert session.disconnected.wait(2)


def test_successful_connect_is_handed_over_untouched():
    session = _GoodSession()
    attempt = ConnectAttempt(
        session=session, port_name="COM5", connect_kwargs={"port": "COM5"}
    )

    assert attempt.run(5) is True
    assert attempt.abandoned is False
    assert attempt.error is None
    assert session.connect_kwargs == {"port": "COM5"}

    # Abandoning after the hand-over must not close an adopted session.
    attempt.abandon(ConnectAttemptCancelled("late"))

    assert attempt.abandoned is False
    assert not session.disconnected.wait(0.2)


def test_driver_exception_is_relayed():
    class _FailingSession(_GoodSession):
        def connect(self, **kwargs):
            raise ValueError("bad frame")

    attempt = ConnectAttempt(session=_FailingSession(), port_name="COM5")

    assert attempt.run(5) is False
    assert attempt.abandoned is False
    assert isinstance(attempt.error, ValueError)


def test_release_closes_a_session_that_never_unblocks(monkeypatch):
    monkeypatch.setattr(connect_attempt, "ABANDONED_CONNECT_RELEASE_S", 0.3)

    class _DeafSession(_StuckSession):
        def connect(self, **kwargs):
            # Ignores cancel_write: only the close can end it.
            self.disconnected.wait()

            raise OSError("port closed")

    session = _DeafSession()
    attempt = ConnectAttempt(session=session, port_name="COM4")

    assert attempt.run(0.1) is False
    assert session.disconnected.wait(3)


# --------------------------------------------------------------------------- #
# Monitor service                                                              #
# --------------------------------------------------------------------------- #


def test_monitor_reports_a_stalled_port_once(monkeypatch):
    monkeypatch.setattr(mod, "DropBotSession", _StuckSession)
    monkeypatch.setattr(mod, "CONNECT_TIMEOUT_S", 0.2)
    harness = _harness()

    assert harness._attempt_connect("COM4") is False
    assert harness._attempt_connect("COM4") is False

    assert "ConnectAttemptTimeout" in harness._last_connect_error
    assert "COM4" in harness._last_connect_error
    assert harness._stalled_ports == {"COM4"}
    assert harness.proxy is None
    assert harness.portable_dropbot_connection_active is False
    assert harness._connect_attempts == []


def test_cleanup_during_a_blocked_connect_returns_promptly(monkeypatch):
    monkeypatch.setattr(mod, "DropBotSession", _StuckSession)
    monkeypatch.setattr(mod, "CONNECT_TIMEOUT_S", 60)
    _StuckSession.instances.clear()
    harness = _harness()
    outcome = {}

    # Stands in for the scheduler's non-daemon pool thread.
    scanner = threading.Thread(
        target=lambda: outcome.update(ok=harness._attempt_connect("COM4"))
    )
    scanner.start()

    assert _wait_until(lambda: len(harness._connect_attempts) == 1)

    started = time.monotonic()
    harness.cleanup()
    scanner.join(2)

    assert time.monotonic() - started < 2
    assert not scanner.is_alive()
    assert outcome == {"ok": False}
    assert "ConnectAttemptCancelled" in harness._last_connect_error
    assert harness.cleaned_up is True

    # The half-open port is closed in the background ...
    assert _StuckSession.instances[0].disconnected.wait(2)

    # ... and nothing non-daemon is left for interpreter exit to join.
    assert all(thread.daemon for thread in _connect_threads())
    assert _wait_until(lambda: not _connect_threads())


def test_no_connect_is_waited_on_once_stopping(monkeypatch):
    monkeypatch.setattr(mod, "DropBotSession", _StuckSession)
    monkeypatch.setattr(mod, "CONNECT_TIMEOUT_S", 60)
    harness = _harness()
    harness._monitor_stopping = True

    started = time.monotonic()

    assert harness._attempt_connect("COM4") is False
    assert time.monotonic() - started < 1


def test_monitor_adopts_a_successful_connect(monkeypatch):
    monkeypatch.setattr(mod, "DropBotSession", _GoodSession)
    monkeypatch.setattr(mod.firmware_versions_publisher, "publish", lambda p: None)
    _GoodSession.instances.clear()
    harness = _harness()

    assert harness._attempt_connect("COM5") is True

    session = _GoodSession.instances[0]

    assert harness.proxy is session
    assert harness.portable_dropbot_connection_active is True
    assert harness.connected_published is True
    assert session.connect_kwargs == {
        "port": "COM5",
        "baudrate": 115200,
        "autodetect": False,
    }
    assert not session.disconnected.is_set()


# --------------------------------------------------------------------------- #
# Port candidates                                                              #
# --------------------------------------------------------------------------- #


def _fake_list_ports(*ports):
    return SimpleNamespace(
        comports=lambda: [
            SimpleNamespace(device=device, description=description)
            for device, description in ports
        ]
    )


_PORTS = (
    ("COM3", "Standard Serial over Bluetooth link (COM3)"),
    ("COM1", "Communications Port (COM1)"),
    ("COM4", "Standard Serial over Bluetooth link (COM4)"),
    ("COM5", "USB Serial Port (COM5)"),
)


def test_candidate_ports_skip_bluetooth_and_sort_usb_first(monkeypatch):
    monkeypatch.setattr(mod, "list_ports", _fake_list_ports(*_PORTS))

    assert _harness()._candidate_ports() == ["COM5", "COM1"]


def test_candidate_ports_put_the_hint_first(monkeypatch):
    monkeypatch.setattr(mod, "list_ports", _fake_list_ports(*_PORTS))
    harness = _harness()
    harness.preferences.port_hint = "COM1"

    assert harness._candidate_ports() == ["COM1", "COM5"]

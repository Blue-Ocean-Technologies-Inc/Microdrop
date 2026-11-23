# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The vendor port lease, as the monitor uses it: a use claim while
connected, and a yield to another process's priority lease (the vendor
flash tool) — disconnect, scanning paused until it lets go plus the release
delay. Fake lease queries and clock; hardware-free, no Redis."""

# Standard library imports.
import os
from types import SimpleNamespace

# Third-party imports.
import pytest
from dropbot_portable.port_lease import PortBusyError

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller.consts import PORT_LEASE_RELEASE_DELAY_S
from portable_dropbot_controller.port_lease_guard import PortLeaseGuard
from portable_dropbot_controller.services import (
    portable_dropbot_monitor_mixin_service as mod,
)

FLASH = {"owner": "flash", "pid": os.getpid() + 1, "phase": "streaming"}


class _FakeLease:
    """Stands in for port_lease.holder / acquire_use and a monotonic clock."""

    def __init__(self):
        self.holders = {}
        self.now = 100.0
        self.released = []

    def holder(self, port):
        return self.holders.get(port)

    def acquire_use(self, port):
        if port in self.holders:
            raise PortBusyError(f"{port} is reserved by a firmware update")

        lease = self

        class _Use:
            def release(self):
                lease.released.append(port)

        return _Use()

    def clock(self):
        return self.now


@pytest.fixture
def lease():
    return _FakeLease()


@pytest.fixture
def guard(lease):
    return PortLeaseGuard(
        lease_holder=lease.holder, acquire_use=lease.acquire_use, clock=lease.clock
    )


def test_own_process_is_never_another_holder(guard, lease):
    lease.holders["COM5"] = {"owner": "flash", "pid": os.getpid()}

    assert guard.other_holder("COM5") is None


def test_a_lease_query_failure_reads_as_no_holder(guard):
    def broken(port):
        raise OSError("lease dir gone")

    guard.lease_holder = broken

    assert guard.other_holder("COM5") is None


def test_claim_is_refused_while_a_flash_holds_the_port(guard, lease):
    lease.holders["COM5"] = FLASH

    with pytest.raises(PortBusyError):
        guard.claim("COM5")


def test_release_drops_the_claim_once(guard, lease):
    guard.claim("COM5")

    guard.release()
    guard.release()

    assert lease.released == ["COM5"]


def test_scan_stays_paused_until_the_holder_is_gone_plus_the_delay(guard, lease):
    lease.holders["COM5"] = FLASH
    guard.begin_yield("COM5", FLASH)

    assert guard.scan_paused() is True

    # The flash finishes: still paused for the release delay.
    del lease.holders["COM5"]
    assert guard.scan_paused() is True

    lease.now += PORT_LEASE_RELEASE_DELAY_S / 2
    assert guard.scan_paused() is True

    lease.now += PORT_LEASE_RELEASE_DELAY_S
    assert guard.scan_paused() is False
    assert guard.yielded_port == ""


def test_a_holder_returning_restarts_the_release_delay(guard, lease):
    guard.begin_yield("COM5", FLASH)
    guard.scan_paused()
    lease.now += PORT_LEASE_RELEASE_DELAY_S * 2

    # A second flash phase takes the lease again before we resumed.
    lease.holders["COM5"] = FLASH
    assert guard.scan_paused() is True

    del lease.holders["COM5"]
    assert guard.scan_paused() is True


def test_not_yielded_never_pauses(guard):
    assert guard.scan_paused() is False


# --------------------------------------------------------------------- #
# The monitor's use of the guard                                         #
# --------------------------------------------------------------------- #
class _Base(HasTraits):
    proxy = Any()
    preferences = Any()
    errors = List()
    disconnected_published = Bool(False)
    realtime_mode = Bool(False)

    def _publish_realtime_mode(self):
        pass

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")

    def _publish_disconnected(self):
        self.disconnected_published = True

    def _publish_status_snapshot(self):
        raise AssertionError("no status poll while the port is yielded")


class _Harness(mod.PortableDropbotMonitorMixinService, _Base):
    pass


class _Session:
    closed = False

    def disconnect(self):
        self.closed = True


@pytest.fixture
def harness(guard):
    return _Harness(port_lease_guard=guard)


def test_a_flash_taking_our_port_disconnects_and_pauses_scanning(harness, lease):
    session = _Session()
    harness.port_lease_guard.claim("COM5")
    harness.proxy = session
    harness.portable_dropbot_connection_active = True
    harness._connected_port = "COM5"
    lease.holders["COM5"] = FLASH

    assert harness._monitor_tick() == []

    assert session.closed
    assert harness.proxy is None
    assert harness.portable_dropbot_connection_active is False
    assert harness.disconnected_published
    assert lease.released == ["COM5"]
    assert "reserved by a firmware update" in harness.errors[0]

    # Disconnected and still held: the tick offers no ports to probe.
    assert harness._monitor_tick() == []


def test_scanning_resumes_after_the_flash_lets_go(harness, lease, monkeypatch):
    monkeypatch.setattr(harness, "_candidate_ports", lambda: ["COM5"])
    harness.port_lease_guard.begin_yield("COM5", FLASH)

    assert harness._monitor_tick() == []

    lease.now += PORT_LEASE_RELEASE_DELAY_S + 1

    assert harness._monitor_tick() == ["COM5"]


def test_scan_probes_skip_a_port_a_flash_holds(harness, lease, monkeypatch):
    tried = []
    monkeypatch.setattr(
        harness, "_attempt_connect", lambda port, autodetect=False: tried.append(port)
    )
    harness.preferences = SimpleNamespace(port_hint="")
    lease.holders["COM5"] = FLASH

    harness._on_ports_discovered(SimpleNamespace(retval=["COM5", "COM6"]))

    assert tried == ["COM6"]

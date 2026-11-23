# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""This process's side of the driver's cross-process serial-port lease
(``dropbot_portable.port_lease``), used the way the vendor UI's worker uses
it: a shared "use" claim on the port while connected, so the vendor flash
tool waits for us to let go, and a yield — disconnect, scanning paused —
whenever another process holds priority on our port, until it lets go.
No Qt, no proxy: unit-testable with fake lease queries."""

# Standard library imports.
import os
import time

# Third-party imports.
from dropbot_portable import port_lease

# Enthought library imports.
from traits.api import Any, Callable, Float, HasTraits, Str, Union

# Local imports.
from .consts import PORT_LEASE_RELEASE_DELAY_S

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PortLeaseGuard(HasTraits):
    """Use claim plus yield state for one connection at a time."""

    #: The lease queries — the vendor worker's injectable ``_lease_holder``
    #: and ``_acquire_use``; tests pass fakes.
    lease_holder = Callable()
    acquire_use = Callable()
    #: Monotonic clock for the release delay; tests pass a fake.
    clock = Callable()

    #: The port handed to a firmware update; empty while not yielded.
    yielded_port = Str()

    #: The shared use claim while connected (``port_lease.PortUse``).
    _port_use = Any()
    #: Clock time the yielded port's lease was first seen released; None
    #: while its holder is still alive.
    _released_at = Union(None, Float)

    def _lease_holder_default(self):
        return port_lease.holder

    def _acquire_use_default(self):
        return port_lease.acquire_use

    def _clock_default(self):
        return time.monotonic

    def other_holder(self, port):
        """The live priority holder's lease info for ``port`` when it is
        another process, else None. A lease-directory glitch never breaks
        the connection (the vendor worker's ``_safe_holder``)."""

        if not port:
            return None

        try:
            info = self.lease_holder(port)
        except Exception as exc:
            logger.debug(f"Port lease query for {port} failed: {exc}")
            return None

        if info is None or info.get("pid") == os.getpid():
            return None

        return info

    def claim(self, port):
        """Register as a cooperating user of ``port`` before opening it.
        Raises ``port_lease.PortBusyError`` while a firmware update holds
        it."""
        self.release()
        self._port_use = self.acquire_use(port)

    def release(self):
        """Drop the use claim — only once the port is closed."""
        use, self._port_use = self._port_use, None

        if use is None:
            return

        try:
            use.release()
        except Exception as exc:
            logger.debug(f"Port lease use release failed: {exc}")

    def begin_yield(self, port, info):
        """Hand ``port`` to the priority holder ``info``: the caller
        disconnects, and scanning stays paused (see scan_paused)."""
        logger.warning(
            f"Portable Dropbot port {port} reserved by a firmware update "
            f"({port_lease.describe(info)}); disconnecting until it finishes."
        )
        self.yielded_port = port
        self._released_at = None

    def end_yield(self):
        """Stop waiting on a yielded port (a user's own connect takes over)."""
        self.yielded_port = ""
        self._released_at = None

    def scan_paused(self):
        """Whether scanning must stay paused for the yielded port: while its
        holder lives and for PORT_LEASE_RELEASE_DELAY_S after it lets go,
        when the yield ends."""

        if not self.yielded_port:
            return False

        if self.other_holder(self.yielded_port) is not None:
            self._released_at = None
            return True

        now = self.clock()

        if self._released_at is None:
            self._released_at = now
            return True

        if now - self._released_at < PORT_LEASE_RELEASE_DELAY_S:
            return True

        logger.info(
            f"Firmware update released port {self.yielded_port}; "
            f"resuming the Portable Dropbot scan."
        )
        self.end_yield()

        return False

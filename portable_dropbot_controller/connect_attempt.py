# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A driver connect that can be abandoned.

The driver opens the port without a write timeout, so a port that is not
the board (a Bluetooth SPP port with no peer, a modem) can swallow the
login write forever (#1065). The connect therefore runs on a daemon thread
the caller waits on with a deadline; on timeout or cancel the caller is
released at once and a daemon release thread unblocks the write, waits for
the driver to give up and closes the session.
"""

# Standard library imports.
import threading
import time

# Enthought library imports.
from traits.api import Any, Bool, Dict, HasTraits, Instance, Str

# Local imports.
from .consts import (
    ABANDONED_CONNECT_POLL_S,
    ABANDONED_CONNECT_RELEASE_S,
    ABANDONED_CONNECT_WRITE_TIMEOUT_S,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class ConnectAttemptTimeout(TimeoutError):
    """The connect gave no answer within its budget and was abandoned."""


class ConnectAttemptCancelled(ConnectionError):
    """The connect was abandoned because the monitor is stopping."""


class ConnectAttempt(HasTraits):
    """One ``session.connect`` call, bounded by a deadline."""

    #: The driver session being connected.
    session = Any()

    #: Serial device the session connects to; names the attempt in logs.
    port_name = Str()

    #: Keyword arguments for ``session.connect``.
    connect_kwargs = Dict()

    #: connect() returned truthy in time.
    succeeded = Bool(False)

    #: Why the attempt failed: the driver's exception, or a timeout/cancel.
    error = Any()

    #: Given up on: the session belongs to the release thread, never adopt it.
    abandoned = Bool(False)

    #: Set when the driver call returned or the attempt was abandoned.
    _finished = Instance(threading.Event, ())

    #: The daemon thread running the driver call.
    _worker = Instance(threading.Thread)

    #: The driver call returned (successfully or not).
    _completed = Bool(False)

    #: run() handed the outcome to its caller; abandon() no longer applies.
    _settled = Bool(False)

    #: Guards the completed/abandoned/settled transitions across threads.
    _state_lock = Any()

    def traits_init(self):
        self._state_lock = threading.Lock()

    def run(self, timeout_s):
        """Connect within ``timeout_s``; return True when the session connected.

        On False, ``error`` says why; when ``abandoned`` is set the session
        is being closed by the release thread and must not be touched.
        """
        with self._state_lock:
            if self.abandoned:
                return False

            self._worker = threading.Thread(
                target=self._connect,
                name=f"portable-connect-{self.port_name}",
                daemon=True,
            )
            self._worker.start()

        self._finished.wait(timeout_s)

        with self._state_lock:
            if self.abandoned:
                return False

            if self._completed:
                self._settled = True

                return self.succeeded

        self.abandon(
            ConnectAttemptTimeout(f"no answer on {self.port_name} within {timeout_s} s")
        )

        return False

    def abandon(self, error):
        """Release the waiting caller now and close the session in the
        background; a no-op once the outcome was handed over."""
        with self._state_lock:
            if self.abandoned or self._settled:
                return

            self.abandoned = True
            self.succeeded = False
            self.error = error

        self._finished.set()
        threading.Thread(
            target=self._release,
            name=f"portable-connect-release-{self.port_name}",
            daemon=True,
        ).start()

    def _connect(self):
        """Worker body: run the driver call and record its outcome."""
        succeeded = False
        error = None

        # Thread boundary: whatever the driver raises (DropBotError,
        # SerialException, an AttributeError from a changed API) is relayed
        # to the waiting caller, which reports it.
        try:
            succeeded = bool(self.session.connect(**self.connect_kwargs))
        except Exception as exc:
            error = exc

        with self._state_lock:
            self._completed = True

            if not self.abandoned:
                self.succeeded = succeeded
                self.error = error

        self._finished.set()

    def _release(self):
        """Unblock the abandoned driver call, let it fail, then close the
        session. Closing first would race the blocked write (pyserial's
        close frees the overlapped write the other thread still waits on)."""
        with self._state_lock:
            worker = self._worker

        deadline = time.monotonic() + ABANDONED_CONNECT_RELEASE_S

        while worker is not None and worker.is_alive() and time.monotonic() < deadline:
            self._unblock_pending_write()
            worker.join(ABANDONED_CONNECT_POLL_S)

        if worker is not None and worker.is_alive():
            logger.warning(
                f"Abandoned Portable Dropbot connect on {self.port_name} is "
                f"still stuck after {ABANDONED_CONNECT_RELEASE_S} s; closing "
                f"the port under it."
            )

        try:
            self.session.disconnect()
        except (OSError, AttributeError) as exc:
            logger.debug(f"Error closing abandoned connect on {self.port_name}: {exc}")

        logger.debug(f"Abandoned connect on {self.port_name} released.")

    def _unblock_pending_write(self):
        """Cancel the write the driver is stuck in and make its next one time
        out, so the login fails instead of blocking again."""
        uart = getattr(self.session, "uart", None)
        port = getattr(uart, "serial", None)

        if port is None or not port.is_open:
            return

        try:
            port.write_timeout = ABANDONED_CONNECT_WRITE_TIMEOUT_S
            port.cancel_write()
        except (OSError, ValueError, AttributeError) as exc:
            logger.debug(f"Could not unblock the connect on {self.port_name}: {exc}")

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure helpers for the fluorescence capture routine (#695): the reply
bookkeeping behind its two frontend round trips (camera controls, saved
frame), an abort-aware wait, the LED's % to raw scaling, and the frame's
file-name tag. No Qt, no driver, no Redis: all unit-testable alone."""

# Standard library imports.
import threading
import time

# Local imports.
from .consts import (
    FLUORESCENCE_LED_PERCENT_BOUNDS,
    FLUORESCENCE_LED_RAW_MAX,
    FLUORESCENCE_WAIT_SLICE_S,
)


class PendingReplies:
    """Replies the routine is waiting for, keyed by request_id.

    The routine calls ``expect`` BEFORE it publishes its request, so a reply
    that beats the wait is still kept; the listener's worker thread calls
    ``resolve``; the routine ``take``s the reply after its wait, which also
    forgets the key. A reply nobody expects is dropped.
    """

    def __init__(self):
        self._lock = threading.Lock()
        #: request_id -> (event, reply payload or None)
        self._pending = {}

    def expect(self, request_id):
        """Register request_id; return the event its reply will set."""
        event = threading.Event()

        with self._lock:
            self._pending[request_id] = (event, None)

        return event

    def resolve(self, request_id, payload):
        """Store a reply and wake its waiter; False when nobody expects it."""
        with self._lock:
            entry = self._pending.get(request_id)

            if entry is None:
                return False

            self._pending[request_id] = (entry[0], payload)

        entry[0].set()

        return True

    def take(self, request_id):
        """Forget request_id; return its reply, or None if none arrived."""
        with self._lock:
            entry = self._pending.pop(request_id, None)

        return None if entry is None else entry[1]


def wait_with_abort(event, abort, timeout_s, slice_s=FLUORESCENCE_WAIT_SLICE_S):
    """Wait up to timeout_s for event, checking abort every slice_s.

    Returns True when event was set, False on timeout or abort; the caller
    tells those two apart with ``abort.is_set()``.
    """
    deadline = time.monotonic() + timeout_s

    while not abort.is_set():
        remaining = deadline - time.monotonic()

        if remaining <= 0:
            return False

        if event.wait(min(slice_s, remaining)):
            return True

    return False


def led_raw(percent):
    """The fluorescence LED's raw 16-bit level for a %, clamped to bounds."""
    low, high = FLUORESCENCE_LED_PERCENT_BOUNDS
    clamped = min(max(int(percent), low), high)

    return round(clamped * FLUORESCENCE_LED_RAW_MAX / 100)

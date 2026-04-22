"""Per-protocol and per-step contexts plus the mailbox machinery that
backs ctx.wait_for().

This file groups Mailbox, wait_first, ProtocolContext, and StepContext
together because they form one cohesive unit — a Mailbox's lifetime is
bound to a StepContext's lifetime, and wait_for is the public method
that ties them together. Splitting them across files would scatter
their tight coupling for no payoff.

ProtocolContext / StepContext land in Task 6 — this task ships only the
two primitives Mailbox depends on.
"""

import queue
import threading
import time
from typing import Callable, Optional

from pluggable_protocol_tree.execution.exceptions import AbortError


def wait_first(events: list, timeout: float) -> Optional[threading.Event]:
    """Block until any of `events` fires, or the timeout elapses.

    Returns the Event that fired, or None on timeout. Implemented by
    polling each event with a short slice — Python's stdlib does not
    expose a kqueue/epoll-style multi-event wait, and rolling a
    waker-channel implementation is more code than the executor needs.

    The poll interval is small enough that responsiveness is dominated
    by the OS scheduler, not by the polling cadence.
    """
    deadline = time.monotonic() + timeout
    poll_interval = 0.01      # 10ms
    while True:
        for e in events:
            if e.is_set():
                return e
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(poll_interval, remaining))


class Mailbox:
    """A SimpleQueue-backed buffer with a wake event.

    One Mailbox per (active step, topic) pair. The dramatiq listener
    deposits payloads; ``drain_one`` blocks until a satisfying item is
    available, the stop_event fires, or the timeout expires.
    """

    def __init__(self):
        self._queue = queue.SimpleQueue()
        self._wake = threading.Event()

    def deposit(self, payload):
        """Push a payload onto the queue and wake any blocked waiter."""
        self._queue.put(payload)
        self._wake.set()

    def drain_one(self, predicate: Optional[Callable], timeout: float,
                  stop_event: threading.Event):
        """Return the first queued item satisfying ``predicate``.

        Discards predicate-rejected items (they are not requeued).
        Raises ``TimeoutError`` if the deadline elapses with no match.
        Raises ``AbortError`` if ``stop_event`` is set, either before
        the call or while the call is blocked.
        """
        if stop_event.is_set():
            raise AbortError("stop_event set before wait_for")
        deadline = time.monotonic() + timeout
        while True:
            # 1) Drain any currently-queued items.
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if predicate is None or predicate(item):
                    return item
                # else discard and continue
            # 2) Block for more.
            self._wake.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"wait_for timed out after {timeout}s"
                )
            triggered = wait_first(
                [self._wake, stop_event], timeout=remaining
            )
            if triggered is None:
                raise TimeoutError(
                    f"wait_for timed out after {timeout}s"
                )
            if triggered is stop_event:
                raise AbortError("stop_event fired while waiting")
            # else self._wake fired; loop back and try to drain.

"""Synchronization primitives used by the executor."""

import threading


class PauseEvent:
    """A pause/resume primitive built on two ``threading.Event``s.

    ``threading.Event`` itself doesn't have a ``wait_cleared()`` method,
    but the executor's main loop needs to block at a step boundary until
    the user resumes — a single Event would only let it block until
    *something* is set, not until the existing 'set' state goes away.
    Implementing it as two events (one fires on set, the other on clear)
    keeps each side a simple Event.wait() under the hood.
    """

    def __init__(self):
        self._set = threading.Event()
        self._cleared = threading.Event()
        self._cleared.set()       # initial state: not paused

    def set(self):
        """Mark paused. wait_cleared() will block until clear() is called."""
        self._set.set()
        self._cleared.clear()

    def clear(self):
        """Mark unpaused. Wakes any thread blocked in wait_cleared()."""
        self._set.clear()
        self._cleared.set()

    def is_set(self) -> bool:
        return self._set.is_set()

    def wait_cleared(self, timeout: float = None) -> bool:
        """Block until the event is cleared (i.e., not paused).

        Returns True if the event was cleared, False on timeout.
        Returns immediately if already clear.
        """
        return self._cleared.wait(timeout)

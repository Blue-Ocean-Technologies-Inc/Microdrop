"""ElapsedTimer — wall-clock elapsed that excludes paused time.

Used by the protocol status bar for the protocol / step / phase timers, so a
pause-then-resume picks up exactly where it left off (paused time is never
counted) and an "elapsed / target" readout can't overflow from pausing.

    t = ElapsedTimer()
    t.reset(running=True)   # step begins
    ...                     # value() climbs
    t.pause()               # freeze (fold the running interval into accum)
    ...                     # value() steady
    t.start()               # resume from where it left off
"""

import time


class ElapsedTimer:
    """Accumulated elapsed seconds plus an optional running interval.

    ``value() == accum + (now - running_since)`` while running, else ``accum``.
    The ``clock`` is injectable for deterministic tests.
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._accum = 0.0
        self._running_since = None

    def reset(self, *, running: bool = False) -> None:
        """Zero the timer; start it running if ``running`` is True."""
        self._accum = 0.0
        self._running_since = self._clock() if running else None

    def start(self) -> None:
        """Begin (or resume) counting. No-op if already running."""
        if self._running_since is None:
            self._running_since = self._clock()

    def pause(self) -> None:
        """Stop counting, folding the running interval into the accumulator.
        No-op if already paused."""
        if self._running_since is not None:
            self._accum += self._clock() - self._running_since
            self._running_since = None

    def value(self) -> float:
        """Elapsed seconds, excluding any paused time."""
        if self._running_since is not None:
            return self._accum + (self._clock() - self._running_since)
        return self._accum

    @property
    def running(self) -> bool:
        return self._running_since is not None

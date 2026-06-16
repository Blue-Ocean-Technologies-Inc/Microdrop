"""Pause-aware stopwatch primitive for protocol status timing (issue #467).

Tracks two clocks for one scope (protocol / step / phase):

  * elapsed -- wall-clock since start; never freezes on pause.
  * active  -- excludes paused intervals; freezes between pause()/resume().

Every method takes ``now`` (a monotonic timestamp) rather than calling the
clock itself, so timing is fully deterministic under test. No Qt, no
threads.
"""


class ScopeStopwatch:
    __slots__ = ("_elapsed_anchor", "_elapsed_accum",
                 "_active_anchor", "_active_accum")

    def __init__(self):
        # monotonic when ticking began; None => stopped/never-started.
        self._elapsed_anchor = None
        self._elapsed_accum = 0.0
        # monotonic of current running segment; None => paused/stopped.
        self._active_anchor = None
        self._active_accum = 0.0

    def start(self, now):
        """(Re)start both clocks from zero; begin ticking and running."""
        self._elapsed_anchor = now
        self._elapsed_accum = 0.0
        self._active_anchor = now
        self._active_accum = 0.0

    def pause(self, now):
        """Freeze the active clock; elapsed keeps ticking."""
        if self._active_anchor is not None:
            self._active_accum += now - self._active_anchor
            self._active_anchor = None

    def resume(self, now):
        """Unfreeze the active clock. No-op if not started or already running."""
        if self._elapsed_anchor is not None and self._active_anchor is None:
            self._active_anchor = now

    def stop(self, now):
        """Freeze BOTH clocks at their current values."""
        if self._active_anchor is not None:
            self._active_accum += now - self._active_anchor
            self._active_anchor = None
        if self._elapsed_anchor is not None:
            self._elapsed_accum += now - self._elapsed_anchor
            self._elapsed_anchor = None

    def elapsed(self, now):
        """Wall-clock seconds since start (ignores pauses)."""
        running = 0.0 if self._elapsed_anchor is None else now - self._elapsed_anchor
        return self._elapsed_accum + running

    def active(self, now):
        """Active seconds since start (excludes paused intervals)."""
        running = 0.0 if self._active_anchor is None else now - self._active_anchor
        return self._active_accum + running

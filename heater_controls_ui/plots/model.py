"""Qt-free rolling buffers backing the heater plots.

Telemetry arrives on the dramatiq worker thread and updates the *latest* value
for each series (sample-and-hold). The canvas timer, on the GUI thread, calls
:meth:`sample` to append one time-aligned point across every series, then
:meth:`snapshot` to read a consistent copy for drawing. All shared buffers are
guarded by a lock, so no Traits->Qt bridge is needed (see the project's
model/controller/view separation).

The plot's run state also lives here so the view stays dumb:

* ``paused``  — the canvas skips sampling and drawing; telemetry still folds
  into the latest values, so resuming continues seamlessly (with a time gap).
* ``enabled`` — False is a full stop: telemetry is ignored and all history is
  cleared. Re-enabling starts from an empty plot.
* ``hidden_series`` — role-prefixed keys the user toggled off via the legend.
* ``revision`` — bumped whenever the drawable buffers change, so the canvas
  can skip redraws when nothing moved.
"""
import threading

from traits.api import Any, Bool, Dict, HasTraits, Instance, Int, List, Set, observe

from .consts import MAX_PLOT_POINTS


class HeaterPlotModel(HasTraits):
    """Time-series buffers for per-sensor temperatures and per-heater PID
    temperature + PWM. Not a status model — it holds no connection state, only
    plottable numbers and the plot's own run state."""

    # ------------------------------------------------------------------ #
    # Run state (set from the GUI; read by the canvas and the listener)    #
    # ------------------------------------------------------------------ #

    paused = Bool(False, desc="Freeze the plot: no sampling ticks or redraws. "
                              "Telemetry still updates the latest values.")
    enabled = Bool(True, desc="False = full stop: telemetry is ignored and "
                              "all history is cleared.")
    hidden_series = Set(desc="Role-prefixed series keys (e.g. 'pid:tec1') "
                             "hidden from the plot via the legend.")
    revision = Int(0, desc="Bumped whenever the drawable buffers change; the "
                           "canvas redraws only when this moves.")

    # ------------------------------------------------------------------ #
    # Buffers (all access under _lock)                                     #
    # ------------------------------------------------------------------ #

    _lock = Instance(threading.Lock)
    _t0 = Any(None)                 # monotonic of the first sample
    # Latest value per key (sample-and-hold between telemetry frames).
    _latest_temps = Dict()          # sensor_name -> float
    _latest_pid = Dict()            # heater -> float
    _latest_pwm = Dict()            # heater -> float
    # Aligned rolling series (same length as _times), None-backfilled for
    # keys that appeared partway through the window.
    _times = List()                 # seconds since first sample
    _sensor_series = Dict()         # sensor_name -> [float|None]
    _pid_series = Dict()            # heater -> [float|None]
    _pwm_series = Dict()            # heater -> [float|None]

    def __lock_default(self):
        return threading.Lock()

    # ------------------------------------------------------------------ #
    # Feed (worker thread)                                                 #
    # ------------------------------------------------------------------ #
    def apply(self, sample):
        """Fold one :func:`telemetry_samples` result into the latest values.
        Ignores empty / unrecognised samples, and everything while disabled."""
        if not sample or not self.enabled:
            return
        with self._lock:
            temps = sample.get("temperatures")
            if temps:
                self._latest_temps.update(temps)
                return
            heater = sample.get("heater")
            if heater is not None:
                if "pid_temperature" in sample:
                    self._latest_pid[heater] = sample["pid_temperature"]
                if "pwm_percentage" in sample:
                    self._latest_pwm[heater] = sample["pwm_percentage"]

    def clear(self):
        """Drop all history and latest values (e.g. on a fresh connection)."""
        with self._lock:
            self._t0 = None
            self._latest_temps.clear()
            self._latest_pid.clear()
            self._latest_pwm.clear()
            self._times.clear()
            self._sensor_series.clear()
            self._pid_series.clear()
            self._pwm_series.clear()
            self.revision += 1

    @observe("enabled")
    def _enabled_updated(self, event):
        # Full stop drops the history so a later re-enable starts fresh (and
        # the revision bump lets the canvas blank the axes once).
        if not event.new:
            self.clear()

    # ------------------------------------------------------------------ #
    # Sample + read (GUI thread)                                           #
    # ------------------------------------------------------------------ #
    def sample(self, now):
        """Append one time-aligned point (seconds since the first sample) using
        the current latest values. No-op until at least one value has arrived,
        so the plot doesn't start with an empty flatline."""
        with self._lock:
            if not (self._latest_temps or self._latest_pid or self._latest_pwm):
                return
            if self._t0 is None:
                self._t0 = now
            self._times.append(now - self._t0)
            length = len(self._times)
            self._extend(self._sensor_series, self._latest_temps, length)
            self._extend(self._pid_series, self._latest_pid, length)
            self._extend(self._pwm_series, self._latest_pwm, length)
            self._trim()
            self.revision += 1

    def snapshot(self):
        """A consistent copy for drawing: ``(times, sensor_series, pid_series,
        pwm_series)`` with the series as ``{key: [values]}`` (lists copied)."""
        with self._lock:
            return (
                list(self._times),
                {k: list(v) for k, v in self._sensor_series.items()},
                {k: list(v) for k, v in self._pid_series.items()},
                {k: list(v) for k, v in self._pwm_series.items()},
            )

    # ------------------------------------------------------------------ #
    # Internals (call with the lock held)                                  #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extend(series, latest, length):
        """Append this tick's value for every key in ``latest``, back-filling
        None for a key seen for the first time so its list aligns with ``_times``."""
        for key, value in latest.items():
            column = series.get(key)
            if column is None:
                column = [None] * (length - 1)
                series[key] = column
            column.append(value)

    def _trim(self):
        if len(self._times) <= MAX_PLOT_POINTS:
            return
        cut = len(self._times) - MAX_PLOT_POINTS
        del self._times[:cut]
        for store in (self._sensor_series, self._pid_series, self._pwm_series):
            for key in store:
                store[key] = store[key][cut:]

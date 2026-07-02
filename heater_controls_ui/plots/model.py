"""Qt-free rolling buffers backing the heater plots.

Telemetry arrives on the dramatiq worker thread and updates the *latest* value
for each series (sample-and-hold). The canvas timer, on the GUI thread, calls
:meth:`sample` to append one time-aligned point across every series, then
:meth:`snapshot` to read a consistent copy for drawing. All shared state is
guarded by a lock, so no Traits->Qt bridge is needed (see the project's
model/controller/view separation).
"""
import threading

from traits.api import HasTraits

from .consts import MAX_PLOT_POINTS


class HeaterPlotModel(HasTraits):
    """Time-series buffers for per-sensor temperatures and per-heater PID
    temperature + PWM. Not a status model — it holds no connection state, only
    plottable numbers."""

    def traits_init(self):
        self._lock = threading.Lock()
        self._t0 = None                 # monotonic of the first sample
        # Latest value per key (sample-and-hold between telemetry frames).
        self._latest_temps = {}         # sensor_name -> float
        self._latest_pid = {}           # heater -> float
        self._latest_pwm = {}           # heater -> float
        # Aligned rolling series (same length as _times), None-backfilled for
        # keys that appeared partway through the window.
        self._times = []                # seconds since first sample
        self._sensor_series = {}        # sensor_name -> [float|None]
        self._pid_series = {}           # heater -> [float|None]
        self._pwm_series = {}           # heater -> [float|None]

    # ------------------------------------------------------------------ #
    # Feed (worker thread)                                                 #
    # ------------------------------------------------------------------ #
    def apply(self, sample):
        """Fold one :func:`telemetry_samples` result into the latest values.
        Ignores empty / unrecognised samples."""
        if not sample:
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
        self._times = self._times[cut:]
        for store in (self._sensor_series, self._pid_series, self._pwm_series):
            for key in store:
                store[key] = store[key][cut:]

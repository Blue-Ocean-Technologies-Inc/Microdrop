# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free live plot of a heater auto-tune run: temperature and heater
output against time, fed one reading at a time from the progress messages,
with a verify run's set point and, after a fit, the fitted
first-order-plus-dead-time response drawn over the capture."""

# Standard library imports.
import math

# Third-party imports.
import numpy as np

# Enthought library imports.
from traits.api import (
    Any,
    ComparisonMode,
    Either,
    Float,
    HasTraits,
    Instance,
    List,
    Tuple,
    observe,
)

# Local imports.
from ..consts import HEATER_TUNE_MODEL_SIM_STEP_S, HEATER_TUNE_PLOT_MAX_SAMPLES

#: Heater output axis range (%), a little headroom above full duty.
OUTPUT_AXIS_PCT = (0.0, 105.0)


def simulate_fopdt(
    times_s,
    inputs_pct,
    gain,
    tau_s,
    dead_time_s,
    y0_c,
    step_s=HEATER_TUNE_MODEL_SIM_STEP_S,
):
    """The first-order-plus-dead-time response at ``times_s`` to the heater
    output ``inputs_pct`` (held between readings), at rest at ``y0_c`` with
    the first output: ``tau dy/dt = -(y - y0) + gain (u(t - dead) - u0)``.
    The vendor's ``heater_tune.simulate_fopdt``, which the frontend cannot
    import."""
    times = np.asarray(times_s, dtype=float)
    inputs = np.asarray(inputs_pct, dtype=float)

    if len(times) < 2:
        return np.full(len(times), float(y0_c))

    grid = np.arange(times[0], times[-1] + step_s, step_s)
    held = np.searchsorted(times, grid - dead_time_s, side="right") - 1
    delayed = inputs[np.clip(held, 0, len(inputs) - 1)] - inputs[0]
    # Before the first reading the plant is at rest (no input change yet).
    delayed[held < 0] = 0.0

    decay = math.exp(-step_s / tau_s)
    response = np.empty_like(delayed)
    state = 0.0

    for index, value in enumerate(delayed):
        response[index] = state
        state = decay * state + (1.0 - decay) * value

    return np.interp(times, grid, y0_c + gain * response)


class HeaterTunePlot(HasTraits):
    """The plot's data and its pyplot-free matplotlib Figure. Structural
    changes (a new run, a set point, a fitted model) draw a new Figure; each
    new reading updates the lines of the current one in place."""

    #: One reading per row: elapsed s, temperature °C, heater output %.
    samples = List(Tuple(Float, Float, Float))

    #: The verify run's set point; None during a capture.
    setpoint_c = Either(None, Float)

    #: The fitted model's response at the readings' times; empty without a
    #: fit.
    model_temperatures_c = List(Float)

    #: The drawn figure; None until the run's first reading. An in-place
    #: update reassigns the same Figure, so comparison is off: the editor
    #: is still notified and redraws its canvas.
    figure = Instance("matplotlib.figure.Figure", comparison_mode=ComparisonMode.none)

    #: The current figure's temperature and output lines.
    _temperature_line = Any()
    _output_line = Any()

    # ------------------------------------------------------------------ #
    # Data                                                                #
    # ------------------------------------------------------------------ #

    def begin(self, setpoint_c=None):
        """Clear the plot for a new run (a verify run's ``setpoint_c``)."""
        self.samples = []
        self.model_temperatures_c = []
        self.setpoint_c = setpoint_c

    def add_reading(self, elapsed_s, current_c, output_pct):
        """Append one reading; a missing temperature is skipped, the oldest
        reading dropped past HEATER_TUNE_PLOT_MAX_SAMPLES."""

        if current_c is None:
            return

        self.samples.append((elapsed_s, current_c, output_pct))
        excess = len(self.samples) - HEATER_TUNE_PLOT_MAX_SAMPLES

        if excess > 0:
            del self.samples[:excess]

    def overlay_fopdt(self, gain, tau_s, dead_time_s, y0_c=None):
        """Draw the fitted model's response to the recorded output; it
        starts at ``y0_c``, the first reading without one."""

        if len(self.samples) < 2 or tau_s <= 0:
            return

        times_s, temperatures_c, outputs_pct = zip(*self.samples)
        start_c = temperatures_c[0] if y0_c is None else y0_c
        response = simulate_fopdt(
            times_s, outputs_pct, gain, tau_s, dead_time_s, start_c
        )

        self.model_temperatures_c = response.tolist()

    # ------------------------------------------------------------------ #
    # Figure                                                              #
    # ------------------------------------------------------------------ #

    @observe("samples, setpoint_c, model_temperatures_c")
    def _redraw_figure(self, event):
        self.figure = self._draw_figure() if self.samples else None

    @observe("samples:items")
    def _update_figure(self, event):
        if self.figure is None:
            self.figure = self._draw_figure()

            return

        self._fill_lines()
        self.figure = self.figure

    def _draw_figure(self):
        # Imported here: only a drawn plot should load matplotlib.
        from matplotlib.figure import Figure

        figure = Figure(figsize=(5, 3), layout="constrained")
        axes = figure.add_subplot()
        output_axes = axes.twinx()

        axes.set_xlabel("Time (s)")
        axes.set_ylabel("Temperature (°C)")
        axes.grid(True)
        output_axes.set_ylabel("Heater output (%)")
        output_axes.set_ylim(*OUTPUT_AXIS_PCT)

        (self._output_line,) = output_axes.plot(
            [], [], color="C1", drawstyle="steps-post", label="Heater output"
        )
        (self._temperature_line,) = axes.plot([], [], color="C0", label="Temperature")

        if self.setpoint_c is not None:
            axes.axhline(self.setpoint_c, color="C2", linestyle="--", label="Set point")

        if self.model_temperatures_c:
            times_s = [sample[0] for sample in self.samples]
            axes.plot(
                times_s[: len(self.model_temperatures_c)],
                self.model_temperatures_c,
                color="C3",
                linestyle=":",
                label="Fitted model",
            )

        lines = axes.get_lines() + output_axes.get_lines()
        axes.legend(lines, [line.get_label() for line in lines], loc="lower right")

        self._fill_lines()

        return figure

    def _fill_lines(self):
        times_s, temperatures_c, outputs_pct = zip(*self.samples)

        self._temperature_line.set_data(times_s, temperatures_c)
        self._output_line.set_data(times_s, outputs_pct)

        # The output axes share the time axis and keep their fixed range.
        axes = self._temperature_line.axes
        axes.relim()
        axes.autoscale_view()

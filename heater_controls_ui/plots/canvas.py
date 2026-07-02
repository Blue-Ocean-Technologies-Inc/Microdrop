"""Matplotlib canvas drawing rolling Temperature and PWM charts.

Two stacked axes (Temperature over PWM). A QTimer samples the model and
redraws on a fixed cadence — telemetry can arrive faster or slower; the plot
runs at its own rate. Colours come from the microdrop_style brand palette and
follow the light/dark theme.
"""
import os
import time

os.environ.setdefault("QT_API", "pyside6")
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from PySide6.QtCore import QTimer

from microdrop_style.colors import GREY, WHITE
from microdrop_style.helpers import is_dark_mode

from .consts import (
    SENSOR_PALETTE, HEATER_PALETTE, DARK_PLOT_BG, LIGHT_PLOT_BG,
    PLOT_UPDATE_INTERVAL_MS,
)


def _theme_colors():
    """(bg, text, grid) for the current app theme."""
    if is_dark_mode():
        return DARK_PLOT_BG, WHITE, GREY["dark"]
    return LIGHT_PLOT_BG, GREY["dark"], GREY["light"]


def _color(palette, index):
    return palette[index % len(palette)]


class HeaterPlotCanvas(FigureCanvasQTAgg):
    """Live Temperature + PWM canvas bound to a :class:`HeaterPlotModel`."""

    def __init__(self, model, parent=None):
        self._model = model
        self._figure = Figure(figsize=(6, 5), tight_layout=True)
        super().__init__(self._figure)
        self.setParent(parent)

        self._temp_ax = self._figure.add_subplot(211)
        self._pwm_ax = self._figure.add_subplot(212)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(PLOT_UPDATE_INTERVAL_MS)

    def stop(self):
        """Stop the redraw timer (call before the widget is destroyed)."""
        if self._timer is not None:
            self._timer.stop()

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    def _tick(self):
        self._model.sample(time.monotonic())
        self._redraw()

    def _redraw(self):
        times, sensors, pids, pwms = self._model.snapshot()
        bg, text, grid = _theme_colors()

        self._figure.patch.set_facecolor(bg)
        self._temp_ax.clear()
        self._pwm_ax.clear()

        # --- Temperature axis: per-sensor temps (solid) + per-heater PID temps
        #     (dashed, in the heater's colour) ---
        for i, name in enumerate(sorted(sensors)):
            values = sensors[name]
            if any(v is not None for v in values):
                self._temp_ax.plot(times, values, "-", linewidth=2, alpha=0.9,
                                   color=_color(SENSOR_PALETTE, i), label=name)
        for h, name in enumerate(sorted(pids)):
            values = pids[name]
            if any(v is not None for v in values):
                self._temp_ax.plot(times, values, "--", linewidth=2, alpha=0.9,
                                   color=_color(HEATER_PALETTE, h),
                                   label=f"{name} (PID)")

        # --- PWM axis: one line per heater (solid, heater colour) ---
        for h, name in enumerate(sorted(pwms)):
            values = pwms[name]
            if any(v is not None for v in values):
                self._pwm_ax.plot(times, values, "-", linewidth=2,
                                  color=_color(HEATER_PALETTE, h), label=name)

        self._style_axis(self._temp_ax, "Temperature", "Temperature (°C)",
                         bg, text, grid, xlabel=None)
        self._style_axis(self._pwm_ax, "Heater PWM", "PWM (%)",
                         bg, text, grid, xlabel="Time (s)")
        self._pwm_ax.set_ylim(-5, 105)

        self.draw_idle()

    @staticmethod
    def _style_axis(ax, title, ylabel, bg, text, grid, xlabel):
        ax.set_facecolor(bg)
        ax.set_title(title, fontsize=11, fontweight="bold", color=text)
        ax.set_ylabel(ylabel, fontsize=9, color=text)
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=9, color=text)
        ax.grid(True, alpha=0.3, color=grid)
        ax.tick_params(colors=text)
        for spine in ax.spines.values():
            spine.set_color(grid)
        handles, _ = ax.get_legend_handles_labels()
        if handles:
            ax.legend(loc="center left", bbox_to_anchor=(1.005, 0.5),
                      facecolor=bg, edgecolor=grid, labelcolor=text, fontsize=8)

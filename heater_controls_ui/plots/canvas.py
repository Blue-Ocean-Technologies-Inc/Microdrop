"""Matplotlib canvas drawing rolling Temperature and PWM charts.

Two stacked axes (Temperature over PWM). A QTimer samples the model and
redraws on a fixed cadence — telemetry can arrive faster or slower; the plot
runs at its own rate. Colours come from the microdrop_style brand palette and
follow the light/dark theme.

Built to stay off the GUI's back:
  * Line2D artists are created once per series and updated with set_data();
    axes are styled once (and again only when the theme flips) and legends are
    rebuilt only when the series set changes — never per tick.
  * The timer stops while the widget is hidden (closed / tabbed-behind pane).
  * Ticks early-out while the model is paused, and redraws are skipped
    entirely when the model's revision hasn't moved (e.g. telemetry stalled).
  * Legend entries are clickable: a pick toggles the series in the model's
    ``hidden_series`` and hidden lines cost nothing to draw.
"""
import math
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
    PLOT_UPDATE_INTERVAL_MS, HIDDEN_LEGEND_ENTRY_ALPHA,
    SENSOR_SERIES_PREFIX, PID_SERIES_PREFIX, PWM_SERIES_PREFIX,
)


def _theme_colors():
    """(bg, text, grid) for the current app theme."""
    if is_dark_mode():
        return DARK_PLOT_BG, WHITE, GREY["dark"]
    return LIGHT_PLOT_BG, GREY["dark"], GREY["light"]


def _color(palette, index):
    return palette[index % len(palette)]


def _nan_backed(values):
    """set_data-friendly copy: None (no reading yet) becomes NaN so matplotlib
    leaves a gap instead of choking on an object array."""
    return [math.nan if v is None else v for v in values]


class HeaterPlotCanvas(FigureCanvasQTAgg):
    """Live Temperature + PWM canvas bound to a :class:`HeaterPlotModel`."""

    def __init__(self, model, parent=None):
        self._model = model
        self._figure = Figure(figsize=(6, 5), tight_layout=True)
        super().__init__(self._figure)
        self.setParent(parent)

        self._temp_ax = self._figure.add_subplot(211)
        self._pwm_ax = self._figure.add_subplot(212)

        # Persistent artists: role-prefixed series key -> Line2D.
        self._sensor_lines = {}
        self._pid_lines = {}
        self._pwm_lines = {}
        # Legend artist (line or text) -> role-prefixed series key.
        self._legend_entry_to_key = {}

        self._drawn_revision = None
        self._theme = None
        self._apply_theme()
        self.mpl_connect("pick_event", self._on_legend_pick)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(PLOT_UPDATE_INTERVAL_MS)

    def stop(self):
        """Stop the redraw timer (call before the widget is destroyed)."""
        self._timer.stop()

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)

    # A hidden pane (closed or tabbed-behind) draws nothing and ticks nothing.
    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        self._timer.start(PLOT_UPDATE_INTERVAL_MS)
        self._tick()                       # catch up immediately on reveal
        super().showEvent(event)

    # ------------------------------------------------------------------ #
    def _tick(self):
        if self._model.paused:
            return
        if self._model.enabled:
            self._model.sample(time.monotonic())
        theme_changed = self._apply_theme()
        if theme_changed or self._model.revision != self._drawn_revision:
            self._drawn_revision = self._model.revision
            self._redraw()

    def _redraw(self):
        times, sensors, pids, pwms = self._model.snapshot()

        # Temperature axis: per-sensor temps (solid) + per-heater PID temps
        # (dashed, in the heater's colour). PWM axis: one line per heater.
        changed = self._update_lines(
            self._temp_ax, self._sensor_lines, times, sensors,
            SENSOR_PALETTE, "-", SENSOR_SERIES_PREFIX, str)
        changed |= self._update_lines(
            self._temp_ax, self._pid_lines, times, pids,
            HEATER_PALETTE, "--", PID_SERIES_PREFIX, "{} (PID)".format)
        changed |= self._update_lines(
            self._pwm_ax, self._pwm_lines, times, pwms,
            HEATER_PALETTE, "-", PWM_SERIES_PREFIX, str)

        if changed:
            self._rebuild_legends()

        self._temp_ax.relim(visible_only=True)
        self._temp_ax.autoscale_view()
        self._pwm_ax.relim(visible_only=True)
        self._pwm_ax.autoscale_view(scaley=False)   # y stays fixed -5..105

        self.draw_idle()

    def _update_lines(self, ax, line_map, times, series, palette, linestyle,
                      key_prefix, label_fn):
        """Sync ``line_map`` to ``series``: create lines for new keys, drop
        vanished ones, push data into the rest. Returns True when the series
        set changed (legend needs a rebuild)."""
        changed = False
        for name in [n for n in line_map if n not in series]:
            line_map.pop(name).remove()
            changed = True
        for i, name in enumerate(sorted(series)):
            line = line_map.get(name)
            if line is None:
                (line,) = ax.plot([], [], linestyle, linewidth=2, alpha=0.9,
                                  label=label_fn(name))
                line_map[name] = line
                changed = True
            line.set_color(_color(palette, i))   # stable by sorted index
            line.set_data(times, _nan_backed(series[name]))
            line.set_visible(f"{key_prefix}{name}" not in self._model.hidden_series)
        return changed

    # ------------------------------------------------------------------ #
    # Legend picking (show / hide individual lines)                        #
    # ------------------------------------------------------------------ #
    def _rebuild_legends(self):
        bg, text, grid = _theme_colors()
        self._legend_entry_to_key.clear()
        # The temperature legend covers both its groups, sensors first.
        self._rebuild_axis_legend(
            self._temp_ax, bg, text, grid,
            [(SENSOR_SERIES_PREFIX, self._sensor_lines),
             (PID_SERIES_PREFIX, self._pid_lines)])
        self._rebuild_axis_legend(
            self._pwm_ax, bg, text, grid,
            [(PWM_SERIES_PREFIX, self._pwm_lines)])

    def _rebuild_axis_legend(self, ax, bg, text, grid, groups):
        keys, handles = [], []
        for key_prefix, line_map in groups:
            for name in sorted(line_map):
                keys.append(f"{key_prefix}{name}")
                handles.append(line_map[name])
        if not handles:
            if ax.get_legend() is not None:
                ax.get_legend().remove()
            return
        legend = ax.legend(
            handles=handles, loc="center left", bbox_to_anchor=(1.005, 0.5),
            facecolor=bg, edgecolor=grid, labelcolor=text, fontsize=8)
        for key, legend_line, legend_text in zip(
                keys, legend.get_lines(), legend.get_texts()):
            legend_line.set_picker(5)
            legend_text.set_picker(True)
            self._legend_entry_to_key[legend_line] = key
            self._legend_entry_to_key[legend_text] = key
            self._style_legend_entry(legend_line, key)

    def _on_legend_pick(self, event):
        key = self._legend_entry_to_key.get(event.artist)
        if key is None:
            return
        hidden = self._model.hidden_series
        if key in hidden:
            hidden.discard(key)
        else:
            hidden.add(key)
        self._apply_visibility()

    def _apply_visibility(self):
        """Re-apply hidden_series to lines + legend entries and rescale to the
        visible lines (a hidden series no longer dictates the axis range)."""
        hidden = self._model.hidden_series
        for key_prefix, line_map in (
                (SENSOR_SERIES_PREFIX, self._sensor_lines),
                (PID_SERIES_PREFIX, self._pid_lines),
                (PWM_SERIES_PREFIX, self._pwm_lines)):
            for name, line in line_map.items():
                line.set_visible(f"{key_prefix}{name}" not in hidden)
        for legend_entry, key in self._legend_entry_to_key.items():
            self._style_legend_entry(legend_entry, key)
        self._temp_ax.relim(visible_only=True)
        self._temp_ax.autoscale_view()
        self._pwm_ax.relim(visible_only=True)
        self._pwm_ax.autoscale_view(scaley=False)
        self.draw_idle()

    def _style_legend_entry(self, legend_entry, key):
        if hasattr(legend_entry, "set_alpha"):
            legend_entry.set_alpha(
                HIDDEN_LEGEND_ENTRY_ALPHA
                if key in self._model.hidden_series else 1.0)

    # ------------------------------------------------------------------ #
    # Theme                                                                #
    # ------------------------------------------------------------------ #
    def _apply_theme(self):
        """Restyle the axes when the app theme flipped. Returns True when a
        restyle happened (the caller forces a redraw)."""
        theme = _theme_colors()
        if theme == self._theme:
            return False
        self._theme = theme
        bg, text, grid = theme
        self._figure.patch.set_facecolor(bg)
        self._style_axis(self._temp_ax, "Temperature", "Temperature (°C)",
                         bg, text, grid, xlabel=None)
        self._style_axis(self._pwm_ax, "Heater PWM", "PWM (%)",
                         bg, text, grid, xlabel="Time (s)")
        self._pwm_ax.set_ylim(-5, 105)
        self._rebuild_legends()
        return True

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

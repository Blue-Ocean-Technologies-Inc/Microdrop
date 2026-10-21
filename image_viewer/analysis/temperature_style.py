# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free styling of the Temperature over time plot view: a row per
heater-log sensor plus the bold line, the capture markers and the
legend. Persisted with the experiment (roi_store); the defaults draw
the view as it looked before it could be styled."""

# Enthought library imports.
from traits.api import Bool, Enum, Float, HasTraits, Instance, List, Range, Str

# Local imports.
from .consts import (
    DEFAULT_ROI_COLORS,
    LINE_STYLE_NAMES,
    MARKER_NAMES,
    ROI_ALPHA_BOUNDS_PCT,
)


class SensorStyle(HasTraits):
    """How one heater-log sensor's trace is drawn."""

    #: The sensor's name in the heater log — the row's key.
    sensor = Str()

    #: Whether the trace is drawn at all.
    visible = Bool(True)

    #: Hex colour, defaulting to the sensor's place in the ROI colour
    #: cycle (see TemperaturePlotStyle.show_sensors).
    color = Str(DEFAULT_ROI_COLORS[0])

    line_style = Enum(*LINE_STYLE_NAMES)
    line_width = Float(0.8)

    #: Opacity as a percentage, as RoiStyle's: the traces are faint so
    #: the chosen sensor's bold line reads over them.
    alpha = Range(*ROI_ALPHA_BOUNDS_PCT, 35, mode="spinner")

    @property
    def plot_alpha(self):
        """``alpha`` as the 0-1 fraction matplotlib wants."""
        return self.alpha / 100.0


class TemperaturePlotStyle(HasTraits):
    """The Temperature over time view's styling."""

    #: A row for every sensor ever styled in this experiment, kept when
    #: a later log lacks one so its styling survives a log that skips it.
    sensors = List(Instance(SensorStyle))

    #: The rows of the sensors the loaded log carries, in its order —
    #: what the panel lists and the plot draws (see show_sensors).
    shown_sensors = List(Instance(SensorStyle))

    #: The figure's chosen sensor (or the mean of them all), drawn bold.
    line_color = Str("#000000")
    line_style = Enum(*LINE_STYLE_NAMES)
    line_width = Float(2.0)

    #: A marker at each analysed capture, in the bold line's colour
    #: unless capture_color_follows_line is switched off.
    capture_marker = Enum("o", MARKER_NAMES)
    capture_size = Float(6.0)
    capture_color_follows_line = Bool(True)
    capture_color = Str("#000000")

    #: Size of the faint hollow markers at excluded captures; their
    #: opacity is the curves view's EXCLUDED_POINT_ALPHA.
    excluded_size = Float(6.0)

    show_legend = Bool(True)

    @property
    def capture_plot_color(self):
        """The colour the capture markers are drawn in."""
        if self.capture_color_follows_line:
            return self.line_color

        return self.capture_color

    def show_sensors(self, names):
        """Point shown_sensors at the rows of ``names`` (the loaded
        log's sensors, in order), adding a default row for any sensor
        not styled before — coloured by its place in the ROI colour
        cycle. Rows of sensors absent from ``names`` stay in
        ``sensors``."""
        rows = {row.sensor: row for row in self.sensors}

        for name in names:
            if name not in rows:
                color = DEFAULT_ROI_COLORS[len(self.sensors) % len(DEFAULT_ROI_COLORS)]
                rows[name] = SensorStyle(sensor=name, color=color)
                self.sensors.append(rows[name])

        self.shown_sensors = [rows[name] for name in names]

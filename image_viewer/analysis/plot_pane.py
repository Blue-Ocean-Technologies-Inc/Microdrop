# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dock pane plotting the ROI intensity series: the chosen stat vs
elapsed time, one line per ROI — or, per the View dropdown, that stat
per ROI on the displayed image (bars) or across the series (violins),
the fits' first- or second-derivative curves, the per-ROI
time-of-fastest-change bars, or that time against the expected one.
A pure observer of the shared analysis model — it derives its own
series from the session (stats store + filters + plot stat) and
coalesces notification bursts into single redraws. Lines gap where an
image failed or isn't computed."""

# Standard library imports.
import math
import os
import re
from pathlib import Path

os.environ.setdefault("QT_API", "pyside6")
import matplotlib

matplotlib.use("QtAgg")

import numpy as np
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoLocator, ScalarFormatter
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pyface.api import OK, DirectoryDialog, FileDialog
from pyface.tasks.api import DockPane
from traits.api import Any, Instance, List, observe
from traitsui.api import (
    EnumEditor,
    HGroup,
    Item,
    Label,
    Tabbed,
    TableEditor,
    UItem,
    VGrid,
    VGroup,
    View,
)

from microdrop_style.icons.icons import (
    ICON_ADD,
    ICON_DELETE,
    ICON_FOLDER_OPEN,
    ICON_FUNCTION,
    ICON_RESTORE,
    ICON_SAVE,
)

from microdrop_utils.traitsui_qt_helpers import (
    DoubleSpinBoxEditor,
    HoverScrollEnumEditor,
    IconButtonEditor,
    IconToggleEditor,
    InPlaceToggleEditor,
    ObjectColumn,
    install_table_clipboard,
    toggle_editor_default_style_sheet_factory,
)

from ..consts import PKG
from ..scale_bar import area_unit
from .consts import (
    BUTTER_CUTOFF_BOUNDS,
    CUSTOM_POINT_ALPHA,
    CUSTOM_POINT_COLOR,
    CUSTOM_POINT_LABEL,
    CUSTOM_POINT_MARKER,
    EXPECTED_METRIC_LABELS,
    EXPECTED_METRIC_MARKERS,
    HEATER_LOGS_DIR_NAME,
    OUTLIER_THRESHOLD_BOUNDS_MAD,
    PLOT_ZOOM_STEP,
    ROI_PLOT_BATCH_COALESCE_MS,
    ROI_PLOT_CANVAS_MIN_HEIGHT,
    ROI_PLOT_CANVAS_MIN_WIDTH,
    ROI_PLOT_COALESCE_MS,
    ROI_PLOT_CONTROLS_MAX_HEIGHT,
    ROI_PLOT_SECTION_MIN_PX,
    X_AXIS_LABELS,
    X_AXIS_MODES,
)
from .curve_fit import (
    FIT_LABELS,
    TREND_METHODS,
    fastest_change_time,
    fit_series,
    linear_trend,
    second_derivative_extrema,
    trimmed_note,
)
from .fit_equations import FitEquationsTable
from .fit_presets import fit_arguments, method_label
from .heater_log import heater_coverage_note
from .plot_series import (
    SMOOTH_LABELS,
    SMOOTH_METHODS,
    analysed_paths,
    analysed_series,
    finite_values,
    image_values,
    interpolated_series,
    smoothed_series,
    x_axis_label,
    x_quantity,
)
from .roi_model import PLOT_STATS, CustomPoint, roi_analysis_model
from .roi_store import analysis_directory
from .roi_table import RoiStatsTable

#: Human labels for the plotted stat (dropdown + y-axis).
PLOT_STAT_LABELS = {
    "mean": "Mean intensity",
    "bg_corrected": "Background-corrected mean",
    "median": "Median intensity",
    "min": "Min intensity",
    "max": "Max intensity",
    "outline_mean": "Outline ring mean",
    "integrated": "Integrated",
    "bg_integrated": "Integrated (bg-corrected)",
    "per_area": "Per area",
    "bg_per_area": "Per area (bg-corrected)",
    "area_normalized": "Mean, area-normalised",
    "bg_area_normalized": "Bg-corrected mean, area-normalised",
    "area": "Area",
    "circularity": "Circularity",
    "shape_change": "Shape change",
    "axis_ratio": "Axis ratio",
    "eccentricity": "Eccentricity",
    "solidity": "Solidity",
    "extent": "Extent",
    "orientation_deg": "Orientation",
}

#: Y-axis wording for the stats whose numbers mean nothing without
#: their unit; every other stat uses its plain label.
_Y_LABEL_TEMPLATES = {
    "per_area": "Intensity per {unit}",
    "bg_per_area": "Bg-corrected intensity per {unit}",
    "area": "Area ({unit})",
    "orientation_deg": "Orientation (°)",
}


def y_axis_label(
    plot_stat,
    scale,
    normalize=False,
    subtract_first=False,
    subtract_background_ref=False,
):
    """The y-axis text for a stat, with the area unit spliced in where
    the stat depends on it and each transform noted where it
    applies."""
    template = _Y_LABEL_TEMPLATES.get(plot_stat)
    label = (
        PLOT_STAT_LABELS[plot_stat]
        if template is None
        else template.format(unit=area_unit(scale.metres_per_pixel, scale.unit))
    )
    # In the order they were applied, so the axis reads as the recipe.
    if subtract_background_ref:
        label = f"{label} (bkg-ref corrected)"
    if subtract_first:
        label = f"{label} (change from first)"
    return f"{label} (% of range)" if normalize else label


def _fit_method_label(key):
    """Dropdown text for a fit key, including the user's own presets
    (which the singleton model carries)."""
    return method_label(key, roi_analysis_model.fit_presets)


#: Points the fitted curve is sampled at for its dashed overlay
#: and the d² view — dense enough to stay smooth at any zoom the
#: pane allows.
FIT_CURVE_SAMPLES = 200

#: The corner equation box, in axes fractions: left margin, the
#: first line's top, and the drop per further line.
EQUATION_BOX_X = 0.02
EQUATION_BOX_TOP_Y = 0.97
EQUATION_LINE_STEP_Y = 0.06

#: Footnotes along the bottom edge, in axes fractions: the
#: log-axis hidden-point count at the bottom, the dropped-outlier
#: count one line above it, the no-temperature count above that, so
#: none of the three ever overprint.
NOTE_HIDDEN_Y = 0.02
NOTE_OUTLIERS_Y = 0.055
NOTE_NO_TEMP_Y = 0.09

#: The views drawn against the time (or temperature) axis; the rest
#: put ROI names along x.
TIME_VIEW_MODES = ("intensity", "first_derivative", "second_derivative")

#: The derivative views' y-axis symbol, by derivative order.
DERIVATIVE_SYMBOLS = {1: "dy/dx", 2: "d²"}

#: The views a log value axis applies to. Not the bar charts: a bar
#: grows from zero, which a log axis cannot show.
LOG_Y_VIEW_MODES = (*TIME_VIEW_MODES, "distribution")

#: A violin body's opacity as a fraction of its ROI's, so the median
#: and extent lines drawn over it stay readable.
VIOLIN_BODY_ALPHA = 0.5

#: The grey wash over a trimmed-away tail: visible over white,
#: faint enough to read the curves through.
TRIM_SHADE_ALPHA = 0.12

#: matplotlib linestyle codes for RoiStyle.line_style.
LINE_STYLES = {"solid": "-", "dashed": "--", "dotted": ":", "dashdot": "-."}

#: Fixed pixel widths, so nothing stretches to fill its row: a value
#: spinner, a small parameter spinner, and a dropdown. Measured in the
#: app's font (Inter 11pt) under the Windows 11 style, whose side-by-side
#: arrows are the widest: a value box shows "-44.7649" or "123456.0" in
#: full, a parameter box "0.25" or "101", a dropdown its longest
#: built-in label ("Actual vs expected"). The plotted-stat dropdown has
#: its own, far wider one for "Bg-corrected mean, area-normalised" —
#: not measured, but scaled from the width measured for "Background-
#: corrected mean" by the ratio of the two labels' text widths.
VALUE_SPIN_W = -138
PARAM_SPIN_W = -102
DROPDOWN_W = -176
STAT_DROPDOWN_W = -315

#: Axis-limit spin boxes: wide enough for any intensity the cameras
#: produce, stepping by a whole count.
AXIS_LIMIT_BOUNDS = (-1e9, 1e9)

#: Temperature-calibration spin boxes: wide enough for any straight
#: line between two thermometers.
TEMPERATURE_SLOPE_BOUNDS = (-1e3, 1e3)
TEMPERATURE_INTERCEPT_BOUNDS = (-1e4, 1e4)
TEMPERATURE_CALIBRATION_TOOLTIP = (
    "Linear calibration applied to the log's temperature before "
    "plotting and fitting: T = slope × T_log + intercept. Use it when "
    "the heater setpoints were compensated against a reference "
    "instrument (fit the two sequences with a straight line to get "
    "slope and intercept). 1 and 0 leave the log's values unchanged."
)


def _section(flag, label, *content):
    """A collapsible group: the image viewer sidebar's chevron header
    over a body that folds away with it. ``flag`` is a Bool on the
    figure settings, so the open/closed state persists with them."""
    return VGroup(
        HGroup(UItem(f"figure.{flag}", editor=IconToggleEditor()), Label(label)),
        VGroup(*content, visible_when=f"figure.{flag}"),
    )


def _axis_spin(name, auto_flag):
    return UItem(
        name,
        width=VALUE_SPIN_W,
        editor=DoubleSpinBoxEditor(
            low=AXIS_LIMIT_BOUNDS[0], high=AXIS_LIMIT_BOUNDS[1], decimals=1, step=1.0
        ),
        enabled_when=f"not figure.{auto_flag}",
    )


def custom_stylesheet(checked):
    return toggle_editor_default_style_sheet_factory(checked, padding="2px 4px")


def _toggle(name, label, enabled_when="", tooltip=""):
    return UItem(
        name,
        editor=InPlaceToggleEditor(
            on_label=label,
            off_label=label,
            custom_style_sheet_factory=custom_stylesheet,
        ),
        enabled_when=enabled_when,
        tooltip=tooltip,
    )


def _top_row():
    """Always visible above the tabs: what is plotted, and the save
    button — saving never needs a tab switch."""
    return HGroup(
        Item(
            "figure.view_mode",
            label="View",
            width=DROPDOWN_W,
            editor=HoverScrollEnumEditor(values_name="model.view_mode_choices"),
        ),
        Item(
            "session.plot_stat",
            label="Plot",
            width=STAT_DROPDOWN_W,
            editor=HoverScrollEnumEditor(
                values=list(PLOT_STATS), format_func=PLOT_STAT_LABELS.get
            ),
        ),
        UItem(
            "model.save_plot_button",
            editor=IconButtonEditor(
                glyph=ICON_SAVE,
                tooltip="Save the plot to the experiment's analysis "
                "folder at the Export tab's DPI and format",
            ),
        ),
    )


def _axes_tab():
    """The axes as a table: rows X and Y, columns Auto / Min / Max /
    Log. The row names the axis, so the Log toggle needs no axis in
    its label."""
    return VGroup(
        VGrid(
            Label(""),
            Label("Auto"),
            Label("Min"),
            Label("Max"),
            Label("Log"),
            Label("X"),
            UItem("figure.x_auto"),
            _axis_spin("figure.x_min", "x_auto"),
            _axis_spin("figure.x_max", "x_auto"),
            UItem(
                "figure.log_x",
                tooltip="Logarithmic x axis. Points at or below 0 "
                "cannot be drawn on it and are counted in "
                "a note on the figure.",
            ),
            Label("Y"),
            UItem("figure.y_auto"),
            _axis_spin("figure.y_min", "y_auto"),
            _axis_spin("figure.y_max", "y_auto"),
            UItem(
                "figure.log_y",
                tooltip="Logarithmic value axis. Zero and negative "
                "values cannot be drawn on it and are "
                "counted in a note on the figure.",
            ),
            columns=5,
            show_labels=False,
        ),
        HGroup(
            Item(
                "figure.x_axis",
                label="X axis",
                width=DROPDOWN_W,
                editor=HoverScrollEnumEditor(
                    values=list(X_AXIS_MODES), format_func=X_AXIS_LABELS.get
                ),
                tooltip="What the curves are plotted against: "
                "elapsed capture time, or the heater log's "
                "temperature at each capture (joined on "
                "wall-clock time). The fits follow it — a "
                "melt midpoint reads in °C.",
            ),
            _toggle(
                "figure.show_legend",
                "Legend",
                tooltip="Show the ROI legend on the figure",
            ),
        ),
        VGroup(
            HGroup(
                Item(
                    "session.heater_log_dir",
                    label="Heater logs",
                    springy=True,
                    tooltip="Folder of the heater's .jsonl logs, joined "
                    "to the captures by wall-clock time; defaults "
                    "to the experiment's heater_logs folder",
                ),
                UItem(
                    "model.heater_dir_button",
                    editor=IconButtonEditor(
                        glyph=ICON_FOLDER_OPEN, tooltip="Choose the heater-log folder"
                    ),
                ),
            ),
            UItem(
                "session.heater_log_hint",
                style="readonly",
                visible_when="session.heater_log_hint",
                tooltip="The folder above covers none of these captures; "
                "the heater log was found in this sibling experiment "
                "instead (not saved as this experiment's folder).",
            ),
            Item(
                "figure.heater_sensor",
                label="Sensor",
                editor=EnumEditor(name="model.heater_sensor_choices"),
                tooltip="Which thermistor the temperature axis "
                "reads; mean averages every sensor on each "
                "log line",
            ),
            Item(
                "figure.heater_window_ms",
                label="Window (ms)",
                width=VALUE_SPIN_W,
                tooltip="How generous the time join is: a "
                "capture's temperature is the mean of "
                "every heater sample within ±window/2 "
                "of it. 0 is exact — interpolation at "
                "the capture instant. Frames with no "
                "sample in the window become gaps.",
            ),
            HGroup(
                Item(
                    "figure.temperature_slope",
                    label="Calibrate: slope",
                    width=VALUE_SPIN_W,
                    editor=DoubleSpinBoxEditor(
                        low=TEMPERATURE_SLOPE_BOUNDS[0],
                        high=TEMPERATURE_SLOPE_BOUNDS[1],
                        decimals=4,
                        step=0.01,
                    ),
                    tooltip=TEMPERATURE_CALIBRATION_TOOLTIP,
                ),
                Item(
                    "figure.temperature_intercept",
                    label="intercept",
                    width=VALUE_SPIN_W,
                    editor=DoubleSpinBoxEditor(
                        low=TEMPERATURE_INTERCEPT_BOUNDS[0],
                        high=TEMPERATURE_INTERCEPT_BOUNDS[1],
                        decimals=4,
                        step=0.1,
                    ),
                    tooltip=TEMPERATURE_CALIBRATION_TOOLTIP,
                ),
            ),
            visible_when="figure.x_axis == 'temperature'",
            show_border=True,
        ),
        label="Axes",
    )


#: When the marker dressing (V-line, H-line, Coords) has a marker to dress.
_ANY_MARKER_SHOWN = (
    "figure.show_second_derivative_max "
    "or figure.show_second_derivative_min "
    "or figure.show_second_derivative_zero"
)


def _fit_tab():
    return VGroup(
        _section(
            "show_method_group",
            "Method",
            HGroup(
                UItem(
                    "figure.fit_method",
                    width=DROPDOWN_W,
                    editor=EnumEditor(
                        name="model.fit_method_choices", format_func=_fit_method_label
                    ),
                ),
                _toggle(
                    "figure.trim_poor_fit",
                    "Trim tail",
                    enabled_when="figure.fit_method != 'none'",
                    tooltip="Refit on a shorter leading slice while "
                    "R² is below 0.99, for series whose tail "
                    "the model does not describe (a bleached "
                    "plateau). The dropped span is shaded.",
                ),
                _toggle(
                    "figure.show_fit_equations",
                    "Equations",
                    enabled_when="figure.fit_method != 'none'",
                    tooltip="Write each ROI's fitted equation into the figure's corner",
                ),
                UItem(
                    "model.fit_equations_button",
                    editor=IconButtonEditor(
                        glyph=ICON_FUNCTION,
                        tooltip="Show the fitted equation for every ROI in a table",
                    ),
                ),
            ),
        ),
        _section(
            "show_metrics_group",
            "Advanced metrics",
            HGroup(
                _toggle(
                    "figure.show_second_derivative_max",
                    "d² max",
                    enabled_when="figure.fit_method != 'none'",
                    tooltip="Mark where the fitted curve's second derivative peaks",
                ),
                _toggle(
                    "figure.show_second_derivative_min",
                    "d² min",
                    enabled_when="figure.fit_method != 'none'",
                    tooltip="Mark where the fitted curve's second derivative troughs",
                ),
                _toggle(
                    "figure.show_second_derivative_zero",
                    "d² zero",
                    enabled_when="figure.fit_method != 'none'",
                    tooltip="Mark where the fitted curve's second derivative "
                    "crosses zero, between the d² max and min: the peak of "
                    "|dy/dx|, where the curve changes fastest — the value the "
                    "Fastest change view and the Expected tab report",
                ),
                _toggle(
                    "figure.second_derivative_vline",
                    "V-line",
                    enabled_when=_ANY_MARKER_SHOWN,
                    tooltip="Drop a vertical line through each marker",
                ),
                _toggle(
                    "figure.second_derivative_hline",
                    "H-line",
                    enabled_when=_ANY_MARKER_SHOWN,
                    tooltip="Run a horizontal line through each marker",
                ),
                _toggle(
                    "figure.second_derivative_coords",
                    "Coords",
                    enabled_when=_ANY_MARKER_SHOWN,
                    tooltip="Write each marker's (x, y) beside it",
                ),
            ),
        ),
        label="Fit",
    )


def _cleanup_tab():
    return VGroup(
        HGroup(
            _toggle(
                "figure.remove_outliers",
                "Outliers",
                tooltip="Drop points that fail the Hampel test — "
                "a rolling median and MAD, so a spike "
                "cannot raise the threshold that would "
                "catch it. Dropped points are counted on "
                "the plot, flagged in the CSV, and kept "
                "out of the fits.",
            ),
            Item(
                "figure.outlier_threshold",
                label="MADs",
                width=PARAM_SPIN_W,
                editor=DoubleSpinBoxEditor(
                    low=OUTLIER_THRESHOLD_BOUNDS_MAD[0],
                    high=OUTLIER_THRESHOLD_BOUNDS_MAD[1],
                    decimals=1,
                    step=0.5,
                ),
                enabled_when="figure.remove_outliers",
                tooltip="How far from the local median counts "
                "as an outlier, in scaled MADs — "
                "about what the same number of "
                "standard deviations would mean for "
                "clean data.",
            ),
            Item(
                "figure.outlier_window",
                label="win",
                width=PARAM_SPIN_W,
                enabled_when="figure.remove_outliers",
                tooltip="Total points in the local window — 5 means "
                "the point plus two each side — used for the "
                "local median and MAD. Wide enough to "
                "describe the trend, narrow enough "
                "not to span a real change.",
            ),
            _toggle(
                "figure.interpolate_gaps",
                "Bridge gaps",
                tooltip="Draw each line straight across its "
                "missing points (dropped outliers, "
                "uncomputed images) instead of breaking "
                "it. Display only — the fits and the CSV "
                "keep the gaps.",
            ),
        ),
        HGroup(
            Item(
                "figure.smooth_method",
                label="Smooth",
                width=DROPDOWN_W,
                editor=EnumEditor(
                    values=list(SMOOTH_METHODS), format_func=SMOOTH_LABELS.get
                ),
                tooltip="Smooth the DRAWN curves only. The fits keep "
                "the unsmoothed points: smoothing makes "
                "neighbouring values dependent, which "
                "flatters R² and shrinks the parameter "
                "uncertainties for the wrong reason.",
            ),
            Item(
                "figure.savgol_window",
                label="win",
                width=PARAM_SPIN_W,
                visible_when="figure.smooth_method == 'savgol'",
                tooltip="Points per polynomial fit (forced odd).",
            ),
            Item(
                "figure.savgol_order",
                label="order",
                width=PARAM_SPIN_W,
                visible_when="figure.smooth_method == 'savgol'",
                tooltip="Polynomial order. Higher follows "
                "sharper features and smooths less.",
            ),
            Item(
                "figure.butter_order",
                label="order",
                width=PARAM_SPIN_W,
                visible_when="figure.smooth_method == 'butterworth'",
                tooltip="Filter order: higher cuts more sharply at the cutoff.",
            ),
            Item(
                "figure.butter_cutoff",
                label="cutoff",
                width=PARAM_SPIN_W,
                editor=DoubleSpinBoxEditor(
                    low=BUTTER_CUTOFF_BOUNDS[0],
                    high=BUTTER_CUTOFF_BOUNDS[1],
                    decimals=2,
                    step=0.01,
                ),
                visible_when="figure.smooth_method == 'butterworth'",
                tooltip="Cutoff as a fraction of the Nyquist "
                "frequency: smaller keeps only the "
                "slowest changes.",
            ),
        ),
        HGroup(
            _toggle(
                "figure.normalize",
                "Normalize",
                tooltip="Stretch each ROI to 0-100% of its own "
                "range, to compare shape and timing "
                "across brightness",
            ),
            _toggle(
                "figure.subtract_first",
                "Subtract first",
                tooltip="Each curve less its own first value: change from baseline",
            ),
            _toggle(
                "figure.subtract_background_ref",
                "Bkg Ref",
                tooltip="Subtract the mean of the ROIs ticked as "
                "Background Ref in the table — a background "
                "reference measured in the same frame. "
                "Stacks with the ring correction and "
                "with Subtract first.",
            ),
        ),
        label="Cleanup",
    )


def _format_fastest_change(value):
    """A fastest-change value for the Expected table, blank when unknown."""
    return "" if value != value else f"{value:.4g}"


#: The Expected tab's table: per ROI per compared landmark, its fitted
#: x value beside the editable expected one. Ctrl+C / Ctrl+V copy and
#: paste blocks of cells (install_table_clipboard). A click selects
#: rather than edits (edit_on_first_click off), so a drag extends the
#: selection and the keys reach the table; double-click to edit.
EXPECTED_TABLE_EDITOR = TableEditor(
    columns=[
        ObjectColumn(name="name", label="ROI", editable=False),
        ObjectColumn(name="label", label="Metric", editable=False),
        ObjectColumn(
            name="actual",
            label="Actual",
            editable=False,
            width=abs(VALUE_SPIN_W),
            format_func=_format_fastest_change,
        ),
        ObjectColumn(
            name="expected",
            label="Expected",
            width=abs(VALUE_SPIN_W),
            format_func=_format_fastest_change,
        ),
    ],
    edit_on_first_click=False,
    selection_mode="cells",
    sortable=False,
)

#: The Expected tab's custom points: typed-in (actual, expected) pairs,
#: removed with the trash button (or the row header's context menu).
#: Ctrl+C / Ctrl+V copy and paste blocks of cells
#: (install_table_clipboard). A click selects rather than edits
#: (edit_on_first_click off); double-click to edit.
CUSTOM_POINTS_TABLE_EDITOR = TableEditor(
    columns=[
        ObjectColumn(name="name", label="Name"),
        ObjectColumn(
            name="actual",
            label="Actual",
            width=abs(VALUE_SPIN_W),
            format_func=_format_fastest_change,
        ),
        ObjectColumn(
            name="expected",
            label="Expected",
            width=abs(VALUE_SPIN_W),
            format_func=_format_fastest_change,
        ),
    ],
    deletable=True,
    edit_on_first_click=False,
    selection_mode="cells",
    selected="model.selected_custom_cells",
    sortable=False,
    row_factory=CustomPoint,
)


def _expected_tab():
    """Per ROI, the x values its fitted landmarks are expected at — and
    any custom points typed in — for the Actual vs expected view."""
    return VGroup(
        HGroup(
            UItem(
                "model.reset_expected_button",
                editor=IconButtonEditor(
                    glyph=ICON_RESTORE,
                    tooltip="Reset every expected value to its actual",
                ),
            ),
            UItem(
                "model.export_expected_button",
                editor=IconButtonEditor(
                    glyph=ICON_SAVE,
                    tooltip="Export the table and the custom points to CSV in "
                    "the experiment's analysis folder (Actual is blank for a "
                    "ROI with no fit)",
                ),
            ),
            _toggle(
                "figure.compare_second_derivative_max",
                "d² max",
                enabled_when="figure.fit_method != 'none'",
                tooltip="Also compare where the fitted curve's second "
                "derivative peaks: adds a row per ROI to the table and a "
                "point per ROI to the Actual vs expected view",
            ),
            _toggle(
                "figure.compare_second_derivative_min",
                "d² min",
                enabled_when="figure.fit_method != 'none'",
                tooltip="Also compare where the fitted curve's second "
                "derivative troughs: adds a row per ROI to the table and a "
                "point per ROI to the Actual vs expected view",
            ),
        ),
        HGroup(
            _toggle(
                "figure.flip_actual_expected",
                "Flip axes",
                enabled_when="figure.view_mode == 'actual_vs_expected'",
                tooltip="Swap the axes: expected on y against actual on x, "
                "so the trend gives expected from actual",
            ),
            Item(
                "figure.trend_method",
                label="Trend",
                width=DROPDOWN_W,
                editor=EnumEditor(
                    values={key: FIT_LABELS[key] for key in TREND_METHODS}
                ),
                enabled_when="figure.view_mode == 'actual_vs_expected'",
                tooltip="The fit drawn through the Actual vs expected "
                "points, its equation written in the corner",
            ),
        ),
        UItem("model.expected_rows", editor=EXPECTED_TABLE_EDITOR),
        _section(
            "show_custom_points_group",
            "Custom points",
            HGroup(
                UItem(
                    "model.add_custom_point_button",
                    editor=IconButtonEditor(
                        glyph=ICON_ADD,
                        tooltip="Add a point typed in by hand — a standard "
                        "of known value, say — plotted and fitted with the "
                        "ROIs in the Actual vs expected view",
                    ),
                ),
                UItem(
                    "model.remove_custom_point_button",
                    editor=IconButtonEditor(
                        glyph=ICON_DELETE,
                        tooltip="Remove the custom points of the selected cells",
                    ),
                    enabled_when="model.selected_custom_cells",
                ),
            ),
            UItem("session.custom_points", editor=CUSTOM_POINTS_TABLE_EDITOR),
        ),
        label="Expected",
    )


def _export_tab():
    """DPI and Format on their own rows; the save button lives on the
    top row, so saving never needs a tab switch."""
    return VGroup(
        HGroup(Item("figure.export_dpi", label="DPI", width=PARAM_SPIN_W)),
        HGroup(Item("figure.export_format", label="Format", width=PARAM_SPIN_W)),
        label="Export",
    )


#: Controls over the per-session plot/export traits, in the tabbed
#: layout settled by review. Rebuilt against the new session on every
#: swap (TraitsUI resolves context objects at build time), which
#: replaces all hand-written widget<->trait syncing; `figure` is its
#: own context key because enabled_when only re-evaluates on trait
#: changes of direct context objects.
_plot_controls_view = View(
    VGroup(
        _top_row(),
        Tabbed(_axes_tab(), _fit_tab(), _cleanup_tab(), _expected_tab(), _export_tab()),
    ),
)

#: Everything the derived series depends on; one observer, one redraw
#: path. Session swap covers experiment changes; stats_revision covers
#: store growth/loads; rois/name for legend labels; plot_stat and
#: filtered_paths for the axes content.
_PLOT_STATE = (
    "session, session:stats_revision, session:rois.items, "
    "session:rois:items:name, session:plot_stat, "
    "session:rois:items:style:color, "
    "session:rois:items:style:line_style, "
    "session:rois:items:style:marker, "
    "session:rois:items:style:marker_size, "
    "session:rois:items:style:visible, "
    "session:rois:items:style:alpha, "
    "session:scale:metres_per_pixel, session:scale:unit, "
    "filtered_paths.items, "
    "session:figure:x_auto, session:figure:x_min, "
    "session:figure:x_max, session:figure:y_auto, "
    "session:figure:y_min, session:figure:y_max, "
    "session:figure:fit_method, "
    "session:figure:custom_expression, "
    "session:figure:trim_poor_fit, "
    "session:figure:show_legend, "
    "session:figure:show_fit_equations, "
    "session:figure:show_second_derivative_max, "
    "session:figure:show_second_derivative_min, "
    "session:figure:show_second_derivative_zero, "
    "session:figure:second_derivative_vline, "
    "session:figure:second_derivative_hline, "
    "session:figure:second_derivative_coords, "
    "session:figure:view_mode, "
    "session:figure:flip_actual_expected, "
    "session:figure:compare_second_derivative_max, "
    "session:figure:compare_second_derivative_min, "
    "session:figure:trend_method, "
    "session:figure:log_x, session:figure:log_y, "
    "session:figure:normalize, "
    "session:figure:subtract_first, "
    "session:figure:subtract_background_ref, "
    "session:figure:remove_outliers, "
    "session:figure:outlier_threshold, "
    "session:figure:outlier_window, "
    "session:figure:interpolate_gaps, "
    "session:figure:x_axis, "
    "session:figure:heater_sensor, "
    "session:figure:heater_window_ms, "
    "session:figure:temperature_slope, "
    "session:figure:temperature_intercept, "
    "session:heater_samples, "
    "session:heater_log_coverage, "
    "session:figure:smooth_method, "
    "session:figure:savgol_window, "
    "session:figure:savgol_order, "
    "session:figure:butter_order, "
    "session:figure:butter_cutoff, "
    "session:rois:items:is_background_ref, "
    "session:rois:items:expected_fastest_change, "
    "session:rois:items:expected_second_derivative_max, "
    "session:rois:items:expected_second_derivative_min, "
    "session:custom_points.items, "
    "session:custom_points:items:name, "
    "session:custom_points:items:actual, "
    "session:custom_points:items:expected"
)

#: Changes that mean "show me everything again", releasing a view the
#: user zoomed or panned into.
_VIEW_RESET_STATE = (
    "session:figure:x_auto, session:figure:y_auto, session:figure:view_mode"
)


class RoiPlotCanvas(FigureCanvasQTAgg):
    """Chart derived from the analysis model, rendering whichever view
    the session's figure settings select."""

    def __init__(self, model):
        # No layout engine: one would re-run on every draw and silently
        # discard the margins set through the toolbar's configure-subplots
        # sliders (and re-fit on savefig, breaking preview == export).
        # tight_layout() once instead, for sensible initial margins.
        self._figure = Figure(figsize=(4, 3))
        super().__init__(self._figure)
        self._model = model
        self._axes = self._figure.add_subplot(111)
        self._axes.set_xlabel(x_axis_label(model.session.figure))
        self._axes.set_ylabel("Mean intensity")
        self._axes.grid(True, alpha=0.3)
        self._figure.tight_layout()
        self._lines = {}
        self._fit_artists = []
        #: Set per redraw: which points the outlier test dropped.
        self._outliers = {}
        #: This redraw's fits, solved on first use (see _fitted_rois).
        self._fits = None
        self._redraw_pending = False
        self._detached = False
        #: Set once the user zooms or pans: their view then survives
        #: every redraw until they ask for a fit.
        self._user_view = False
        self._panning = False
        model.observe(self._on_plot_state_changed, _PLOT_STATE)
        model.observe(self._on_fit_requested, _VIEW_RESET_STATE)
        model.observe(self._on_displayed_image_changed, "current_image_path")
        for event_name, handler in (
            ("scroll_event", self._on_scroll),
            ("button_press_event", self._on_press),
            ("motion_notify_event", self._on_motion),
            ("button_release_event", self._on_release),
        ):
            self.mpl_connect(event_name, handler)
        self._schedule_redraw()

    # ------------------------------------------------------------------ #
    # Modeless zoom and pan, as on the image canvas next door: the        #
    # navigation toolbar's own tools still work and take precedence.      #
    # ------------------------------------------------------------------ #
    def release_view(self):
        """Drop the user's view and let the axes autoscale again."""
        self._user_view = False
        self._schedule_redraw()

    def _on_fit_requested(self, event):
        self.release_view()

    def _toolbar_busy(self):
        """True while the navigation toolbar's pan or zoom tool is armed
        (or anything else holds the canvas), so the two never fight."""
        return bool(
            getattr(getattr(self, "toolbar", None), "mode", "")
            or self.widgetlock.locked()
        )

    def _on_scroll(self, event):
        if self._toolbar_busy() or event.inaxes is not self._axes:
            return
        factor = PLOT_ZOOM_STEP if event.button == "up" else 1.0 / PLOT_ZOOM_STEP
        x_limits = self._zoomed(
            self._axes.xaxis.get_transform(), self._axes.get_xlim(), event.xdata, factor
        )
        y_limits = self._zoomed(
            self._axes.yaxis.get_transform(), self._axes.get_ylim(), event.ydata, factor
        )
        if x_limits is None or y_limits is None:
            return
        self._axes.set_xlim(x_limits)
        self._axes.set_ylim(y_limits)
        self._user_view = True
        self.draw_idle()

    @staticmethod
    def _zoomed(transform, limits, cursor, factor):
        """The new (low, high) about ``cursor``, computed in the axis's
        own scale so a notch multiplies on a log axis and adds on a
        linear one. None when the scale cannot represent them."""
        if cursor is None:
            return None
        low, high, point = transform.transform([limits[0], limits[1], cursor])
        if not np.all(np.isfinite([low, high, point])):
            return None
        scaled = [point - (point - low) * factor, point + (high - point) * factor]
        new_low, new_high = transform.inverted().transform(scaled)
        if not np.all(np.isfinite([new_low, new_high])) or new_low >= new_high:
            return None
        return new_low, new_high

    def _on_press(self, event):
        if self._toolbar_busy() or event.button != 1 or event.inaxes is not self._axes:
            return
        # Matplotlib's own pan machinery, which already knows how each
        # axis scale moves.
        self._axes.start_pan(event.x, event.y, event.button)
        self._panning = True

    def _on_motion(self, event):
        if not self._panning:
            return
        self._axes.drag_pan(1, event.key, event.x, event.y)
        self._user_view = True
        self.draw_idle()

    def _on_release(self, event):
        if not self._panning:
            return
        self._axes.end_pan()
        self._panning = False

    def detach(self):
        # An in-flight coalesced singleShot may fire after the widget's
        # C++ side is gone; the flag makes it a no-op.
        self._detached = True
        self._model.observe(self._on_plot_state_changed, _PLOT_STATE, remove=True)
        self._model.observe(self._on_fit_requested, _VIEW_RESET_STATE, remove=True)
        self._model.observe(
            self._on_displayed_image_changed, "current_image_path", remove=True
        )

    def showEvent(self, event):
        self._schedule_redraw()  # catch up on anything missed hidden
        super().showEvent(event)

    def _on_plot_state_changed(self, event):
        self._schedule_redraw()

    def _on_displayed_image_changed(self, event):
        # Only the per-image view reads the displayed image; redrawing
        # the others would refit every ROI on each step through the
        # series for nothing.
        if self._model.session.figure.view_mode == "per_image":
            self._schedule_redraw()

    def _schedule_redraw(self):
        if self._redraw_pending:
            return
        self._redraw_pending = True
        # A running batch drains in bursts and every redraw refits each
        # ROI, so at the idle cadence the redraws would crowd out the
        # progress readout; back off until the batch finishes.
        QTimer.singleShot(
            ROI_PLOT_BATCH_COALESCE_MS
            if self._model.batch_running
            else ROI_PLOT_COALESCE_MS,
            self._refresh,
        )

    def _refresh(self):
        self._redraw_pending = False
        if self._detached:
            return
        if not self.isVisible():
            return  # showEvent reschedules
        session = self._model.session
        # One pipeline, shared with the export, so a saved fit and the
        # drawn one cannot disagree about which points they saw.
        series, self._outliers = analysed_series(session, self._model.filtered_paths)
        figure_settings = session.figure
        self._fits = None
        for artist in self._fit_artists:
            artist.remove()
        self._fit_artists = []
        # A previous fastest-change render left categorical ticks behind.
        self._axes.xaxis.set_major_locator(AutoLocator())
        self._axes.xaxis.set_major_formatter(ScalarFormatter())
        self._axes.set_xlabel(x_axis_label(figure_settings))
        # After the locator reset above (which would fight the log
        # locators), before relim, so autoscale sees the final scale,
        # and before drawing: setting a scale resets the axis locators,
        # which would wipe the ROI-name ticks the bar and violin views
        # set. Those views keep a linear x.
        view_mode = figure_settings.view_mode
        time_axis = view_mode in TIME_VIEW_MODES
        log_x = time_axis and figure_settings.log_x
        log_y = view_mode in LOG_Y_VIEW_MODES and figure_settings.log_y
        self._axes.set_xscale("log" if log_x else "linear")
        self._axes.set_yscale("log" if log_y else "linear")

        if view_mode == "intensity":
            trim_edges = self._refresh_intensity(series, figure_settings)
        else:
            for roi_id in list(self._lines):
                self._lines.pop(roi_id).remove()

            if view_mode == "first_derivative":
                trim_edges = self._draw_derivative(series, figure_settings, 1)
            elif view_mode == "second_derivative":
                trim_edges = self._draw_derivative(series, figure_settings, 2)
            elif view_mode == "per_image":
                trim_edges = self._draw_per_image(series, figure_settings)
            elif view_mode == "distribution":
                trim_edges = self._draw_distribution(series, figure_settings)
            elif view_mode == "fastest_change":
                trim_edges = self._draw_fastest_change(series, figure_settings)
            else:
                trim_edges = self._draw_actual_vs_expected(series, figure_settings)

        # The Expected tab and its CSV read these whatever is shown. The
        # fitting views reuse their fits; the per-image and distribution
        # views fit nothing, so they pay one fit pass here to keep the
        # actuals current.
        self._model.expected_actuals = {
            roi.roi_id: landmarks
            for roi, _name, landmarks in self._fit_landmarks(series, figure_settings)
        }

        # A view the user zoomed or panned into outlives every redraw
        # — a drained result or a toggled fit would otherwise snap the
        # axes back while they were still reading them.
        kept = (
            (self._axes.get_xlim(), self._axes.get_ylim()) if self._user_view else None
        )
        if kept is None:
            # set_xlim during a zoom latches autoscaling off, so without
            # this the axes would never rescale again — not for new
            # data, not even for Home.
            self._axes.set_autoscale_on(True)
        self._axes.relim()
        self._axes.autoscale_view()
        if kept is not None:
            self._axes.set_xlim(kept[0])
            self._axes.set_ylim(kept[1])
        # A log axis rejects a limit at or below zero, so a manual one
        # is skipped there and the autoscaled range stands.
        if (
            not figure_settings.x_auto
            and time_axis
            and not (log_x and figure_settings.x_min <= 0)
        ):
            self._axes.set_xlim(figure_settings.x_min, figure_settings.x_max)
        if not figure_settings.y_auto and not (log_y and figure_settings.y_min <= 0):
            self._axes.set_ylim(figure_settings.y_min, figure_settings.y_max)
        # After the scaling: the band is full-height in axes fractions,
        # so relim() would read those as data and pin the y limits.
        self._shade_trimmed_tails(trim_edges)
        self._note_hidden_points(series, log_x, log_y)
        self._note_dropped_outliers()

        # The per-ROI stat views draw every value whatever its
        # temperature, so frames the log misses are not missing there.
        if view_mode not in ("per_image", "distribution"):
            self._note_missing_temperatures(series, figure_settings)

        self.draw_idle()

    def _refresh_intensity(self, series, figure_settings):
        session = self._model.session
        # Smoothing is a display aid, so it goes no further than the
        # lines: `series` — unsmoothed — is what the fits below see.
        drawn = (
            smoothed_series(
                series,
                figure_settings.smooth_method,
                figure_settings.savgol_window,
                figure_settings.savgol_order,
                figure_settings.butter_cutoff,
            )
            if figure_settings.smooth_method != "none"
            else series
        )
        # After the smoothing, so a bridge spans between the smoothed
        # neighbours rather than cutting under them.
        if figure_settings.interpolate_gaps:
            drawn = interpolated_series(drawn)
        self._axes.set_ylabel(self._stat_axis_label(figure_settings))
        for roi_id in list(self._lines):
            if roi_id not in drawn:
                self._lines.pop(roi_id).remove()
        for roi_id, (name, elapsed, values) in drawn.items():
            if roi_id not in self._lines:
                (self._lines[roi_id],) = self._axes.plot([], [])
            line = self._lines[roi_id]
            line.set_data(elapsed, values)
            line.set_label(name)
            roi = self._model.session.roi_by_id(roi_id)
            if roi is not None:
                line.set_color(roi.style.color)
                line.set_linestyle(LINE_STYLES[roi.style.line_style])
                line.set_marker("" if roi.style.marker == "none" else roi.style.marker)
                line.set_markersize(roi.style.marker_size)
                line.set_alpha(roi.style.plot_alpha)
        if not series and session.positive_rois:
            self._draw_hint("All ROIs are hidden (eye icons in the table)")
        elif figure_settings.subtract_background_ref and not any(
            roi.is_background_ref for roi in session.positive_rois
        ):
            # Asked of the session, not the drawn series: a reference
            # that is merely hidden still corrects, and saying it does
            # not would be worse than saying nothing.
            self._draw_hint(
                "No ROI is ticked as Bkg Ref, so there is "
                "no background reference to subtract"
            )
        trim_edges = []
        if figure_settings.fit_method != "none":
            trim_edges = self._draw_fits(series, figure_settings)
        self._apply_legend(bool(self._lines) and figure_settings.show_legend)
        return trim_edges

    def _stat_axis_label(self, figure_settings):
        """The plotted stat's y-axis text with its transforms noted —
        shared by every view that draws the stat itself."""
        session = self._model.session

        return y_axis_label(
            session.plot_stat,
            session.scale,
            figure_settings.normalize,
            figure_settings.subtract_first,
            figure_settings.subtract_background_ref,
        )

    def _draw_per_image(self, series, figure_settings):
        """Bar per visible ROI: the plotted stat on the displayed image.
        A cross-section of the time view at that image, corrections
        and all, so the two always agree; it follows the viewer's
        selection."""
        session = self._model.session
        image_path = self._model.current_image_path
        paths = analysed_paths(session, self._model.filtered_paths)
        values = image_values(series, paths, image_path)

        self._axes.set_ylabel(self._stat_axis_label(figure_settings))
        self._axes.set_xlabel(f"ROI — {Path(image_path).name}" if image_path else "ROI")
        self._apply_legend(False)

        if not image_path:
            self._draw_hint("No image displayed")

            return []

        if values is None:
            self._draw_hint(
                "The displayed image is excluded from analysis"
                if session.is_excluded(image_path)
                else "The displayed image is not in the filtered series"
            )

            return []

        entries = []

        for roi_id, (name, value) in values.items():
            roi = session.roi_by_id(roi_id)

            if roi is not None:
                entries.append((name, value, roi.style))

        if not any(value == value for _name, value, _style in entries):
            self._draw_hint("No stats computed for the displayed image")

            return []

        self._draw_roi_bars(entries)

        return []  # ROI names on x: no time span to shade

    def _draw_distribution(self, series, figure_settings):
        """Violin per visible ROI: the spread of the plotted stat
        across the analysed images, its median marked. A ROI with no
        computed value gets no violin."""
        session = self._model.session
        samples = []

        for roi_id, (name, values) in finite_values(series).items():
            roi = session.roi_by_id(roi_id)

            if roi is not None:
                samples.append((name, values, roi.style))

        self._axes.set_ylabel(self._stat_axis_label(figure_settings))
        self._axes.set_xlabel("ROI")
        self._apply_legend(False)

        if not samples:
            self._draw_hint("No computed values to show a distribution of")

            return []

        positions = list(range(len(samples)))
        violins = self._axes.violinplot(
            [values for _name, values, _style in samples],
            positions,
            showmedians=True,
        )
        colors = [style.color for _name, _values, style in samples]

        for body, (_name, _values, style) in zip(violins["bodies"], samples):
            body.set_facecolor(style.color)
            body.set_edgecolor(style.color)
            body.set_alpha(VIOLIN_BODY_ALPHA * style.plot_alpha)

        # The bodies come as a list, the median and extent lines as one
        # collection each; every one of them goes at the next redraw.
        for key, artists in violins.items():
            if key == "bodies":
                self._fit_artists.extend(artists)
            else:
                artists.set_color(colors)
                self._fit_artists.append(artists)

        self._axes.set_xticks(positions, [name for name, _values, _style in samples])

        return []  # ROI names on x: no time span to shade

    def _draw_roi_bars(self, entries):
        """Bar per (name, height, style) entry, coloured and faded by
        the ROI's style and labelled with its value. A NaN height keeps
        its slot as an empty bar marked n/a, so a ROI never shifts
        along x when one image lacks it."""
        positions = list(range(len(entries)))
        # Keep the container, not its bars: its remove() also drops the
        # axes.containers registration the bars alone would leave behind.
        bars = self._axes.bar(
            positions,
            [0.0 if height != height else height for _name, height, _style in entries],
            color=[style.color for _name, _height, style in entries],
        )

        for bar, (_name, _height, style) in zip(bars, entries):
            bar.set_alpha(style.plot_alpha)

        self._fit_artists.append(bars)
        self._axes.set_xticks(positions, [name for name, _height, _style in entries])

        for x, (_name, height, _style) in zip(positions, entries):
            missing = height != height

            self._fit_artists.append(
                self._axes.annotate(
                    "n/a" if missing else f"{height:.3g}",
                    (x, 0.0 if missing else height),
                    textcoords="offset points",
                    xytext=(0, 4),
                    ha="center",
                    fontsize="x-small",
                    color="gray" if missing else None,
                )
            )

    def _fitted_rois(self, series, figure_settings):
        """(roi, name, fit, finite_t) per ROI the chosen method fits,
        finite_t being its x at the finite values — never empty, as
        fit_series needs two finite points. ROIs that cannot be fitted
        are skipped. Solved once per redraw: every later call in the
        same redraw gets the same list."""
        if self._fits is None:
            self._fits = list(self._solve_fits(series, figure_settings))

        return self._fits

    def _solve_fits(self, series, figure_settings):
        """Yield the fits _fitted_rois holds for the redraw."""
        method, expression = fit_arguments(figure_settings, self._model.fit_presets)

        for roi_id, (name, elapsed, values) in series.items():
            roi = self._model.session.roi_by_id(roi_id)

            if roi is None:
                continue

            fit = fit_series(
                elapsed,
                values,
                method,
                figure_settings.trim_poor_fit,
                expression,
                figure_settings.initial_guesses,
            )

            if fit is None:
                continue

            finite_t = np.asarray(elapsed, dtype=float)[
                np.isfinite(np.asarray(values, dtype=float))
            ]

            yield roi, name, fit, finite_t

    def _draw_derivative(self, series, figure_settings, order):
        """One curve per ROI: the fitted model's first or second
        derivative over the ROI's span. The fastest-change marker sits
        on either; the d² max/min ones on the second only."""
        symbol = DERIVATIVE_SYMBOLS[order]

        self._axes.set_ylabel(f"{symbol} of fit")

        if figure_settings.fit_method == "none":
            self._apply_legend(False)
            self._draw_hint(f"Select a fit method to view {symbol}")

            return []

        drew, trim_edges = False, []

        for roi, name, fit, finite_t in self._fitted_rois(series, figure_settings):
            derivative = fit.first_derivative if order == 1 else fit.second_derivative
            trim_edges.append((fit.fitted_end, finite_t.max()))
            dense = np.linspace(finite_t.min(), finite_t.max(), FIT_CURVE_SAMPLES)
            curve_values = np.asarray(derivative(dense), dtype=float)

            if curve_values.shape != dense.shape:  # scalar-returning closure
                curve_values = np.full_like(dense, float(curve_values))

            (curve,) = self._axes.plot(
                dense,
                curve_values,
                color=roi.style.color,
                alpha=roi.style.plot_alpha,
                label=name,
            )
            self._fit_artists.append(curve)
            drew = True

            self._draw_extrema(
                fit,
                finite_t.min(),
                finite_t.max(),
                roi,
                figure_settings,
                marker_y=derivative,
                with_second_derivative_extrema=order == 2,
            )

        self._apply_legend(drew and figure_settings.show_legend)

        return trim_edges

    def _fit_landmarks(self, series, figure_settings):
        """(roi, name, {metric: x}) per fitted ROI, keyed by
        EXPECTED_METRICS: "zero" where its fitted curve changes fastest
        (max |dy/dx|, where d² crosses zero — a sigmoid's inflection
        point), and, while the Expected tab compares them, "max" / "min"
        where d² peaks / troughs. A landmark the fit lacks (a linear
        fit's rate is flat, a quadratic's d² too) is left out, and so is
        a ROI with none."""
        extrema_wanted = [
            metric for metric in figure_settings.compared_metrics if metric != "zero"
        ]
        landmarks = []

        for roi, name, fit, finite_t in self._fitted_rois(series, figure_settings):
            t_start, t_end = finite_t.min(), finite_t.max()
            found = {}
            fastest = fastest_change_time(fit, t_start, t_end)

            if fastest is not None:
                found["zero"] = fastest

            if extrema_wanted:
                extrema = second_derivative_extrema(fit, t_start, t_end)
                found.update(
                    {
                        metric: extrema[metric][0]
                        for metric in extrema_wanted
                        if metric in extrema
                    }
                )

            if found:
                landmarks.append((roi, name, found))

        return landmarks

    def _fastest_change_points(self, series, figure_settings):
        """(roi, name, actual) per ROI with a fastest-change point — the
        "zero" landmark of _fit_landmarks."""
        return [
            (roi, name, landmarks["zero"])
            for roi, name, landmarks in self._fit_landmarks(series, figure_settings)
            if "zero" in landmarks
        ]

    def _draw_fastest_change(self, series, figure_settings):
        """Bar per ROI: seconds until the fitted curve changes fastest
        (max |dy/dt| — a sigmoid's inflection point). ROIs whose fit
        fails or whose speed is flat (linear) get no bar."""
        quantity, unit = x_quantity(figure_settings)

        self._axes.set_ylabel(f"{quantity} of fastest change ({unit})")
        self._axes.set_xlabel("ROI")
        self._apply_legend(False)

        if figure_settings.fit_method == "none":
            self._draw_hint("Select a fit method to view fastest change")

            return []

        entries = [
            (name, actual, roi.style)
            for roi, name, actual in self._fastest_change_points(
                series, figure_settings
            )
        ]

        if not entries:
            self._draw_hint(
                "No fastest-change points (fits failed or rate is constant)"
            )

            return []

        self._draw_roi_bars(entries)

        return []  # ROI names on x: no time span to shade

    def _draw_actual_vs_expected(self, series, figure_settings):
        """Point per ROI per compared landmark — the fastest change, and
        the d² max / min when the Expected tab compares them — its fitted
        x value against the one the user expects (the Expected tab; unset
        reads as the actual), plus the custom points typed in there, over
        the identity line, with a trend fitted through them all whose
        equation goes in the corner. Flipped, expected goes on y, so the
        trend gives expected from actual."""
        quantity, unit = x_quantity(figure_settings)
        metrics = figure_settings.compared_metrics
        measured = (
            f"{quantity.lower()} of fastest change ({unit})"
            if metrics == ["zero"]
            else f"{quantity.lower()} at "
            + " / ".join(EXPECTED_METRIC_LABELS[metric] for metric in metrics)
            + f" ({unit})"
        )
        x_name, y_name = (
            ("actual", "expected")
            if figure_settings.flip_actual_expected
            else ("expected", "actual")
        )

        self._axes.set_xlabel(f"{x_name.capitalize()} {measured}")
        self._axes.set_ylabel(f"{y_name.capitalize()} {measured}")
        self._apply_legend(False)

        if figure_settings.fit_method == "none":
            self._draw_hint("Select a fit method to view actual vs expected")

            return []

        points = [
            (roi, name, metric, actual)
            for roi, name, landmarks in self._fit_landmarks(series, figure_settings)
            for metric, actual in landmarks.items()
        ]
        custom_points = [
            point
            for point in self._model.session.custom_points
            if math.isfinite(point.actual) and math.isfinite(point.expected)
        ]

        if not points and not custom_points:
            self._draw_hint(
                "No fastest-change points (fits failed or rate is constant)"
            )

            return []

        # The custom points follow the ROIs' in every list below, so
        # they join the trend fit like any other point.
        values = {
            "expected": [
                roi.expected_or(metric, actual) for roi, _name, metric, actual in points
            ]
            + [point.expected for point in custom_points],
            "actual": [actual for _roi, _name, _metric, actual in points]
            + [point.actual for point in custom_points],
        }
        x_values, y_values = values[x_name], values[y_name]
        span = [min(*x_values, *y_values), max(*x_values, *y_values)]

        # (name, marker, colour, alpha) per point, in x_values order.
        dressing = [
            (
                name,
                EXPECTED_METRIC_MARKERS[metric],
                roi.style.color,
                roi.style.plot_alpha,
            )
            for roi, name, metric, _actual in points
        ] + [
            (point.name, CUSTOM_POINT_MARKER, CUSTOM_POINT_COLOR, CUSTOM_POINT_ALPHA)
            for point in custom_points
        ]
        markers = list(
            dict.fromkeys(marker for _name, marker, _color, _alpha in dressing)
        )

        (identity_line,) = self._axes.plot(
            span,
            span,
            linestyle="--",
            linewidth=0.8,
            color="gray",
            alpha=0.6,
            label="_nolegend_",
        )
        self._fit_artists.append(identity_line)

        for marker in markers:
            members = [
                (x, y, color, alpha)
                for x, y, (_name, point_marker, color, alpha) in zip(
                    x_values, y_values, dressing
                )
                if point_marker == marker
            ]
            xs, ys, colors, alphas = zip(*members)

            self._fit_artists.append(
                self._axes.scatter(
                    xs,
                    ys,
                    marker=marker,
                    color=list(colors),
                    alpha=list(alphas),
                    zorder=3,
                )
            )

        for (name, _marker, _color, _alpha), x, y in zip(dressing, x_values, y_values):
            self._fit_artists.append(
                self._axes.annotate(
                    name,
                    (x, y),
                    textcoords="offset points",
                    xytext=(6, 4),
                    fontsize="x-small",
                )
            )

        # One marker shape needs no key; several (or a custom point,
        # which no ROI colour names) get one, in black so it reads as
        # the shape alone.
        if len(markers) > 1 or custom_points:
            marker_labels = {
                EXPECTED_METRIC_MARKERS[metric]: EXPECTED_METRIC_LABELS[metric]
                for metric in metrics
            }
            marker_labels[CUSTOM_POINT_MARKER] = CUSTOM_POINT_LABEL

            self._fit_artists.append(
                self._axes.legend(
                    handles=[
                        Line2D(
                            [],
                            [],
                            marker=marker,
                            color="black",
                            linestyle="",
                            label=marker_labels[marker],
                        )
                        for marker in markers
                    ],
                    loc="lower right",
                    fontsize="x-small",
                )
            )

        self._draw_trend(
            x_values, y_values, x_name, y_name, figure_settings.trend_method
        )

        return []  # landmark x values on both axes: no time span

    def _draw_trend(self, x_values, y_values, x_name, y_name, method):
        """The Actual vs expected trend: a ``method`` fit (a
        TREND_METHODS key) through the points, dashed over their x
        range, with its equation and R² in the corner — or a corner
        note when the points are too few for it."""
        if method == "linear":
            trend = linear_trend(x_values, y_values)

            if trend is None:
                return

            slope, intercept, r_squared = trend
            trend_x = np.array([min(x_values), max(x_values)])
            # Unset expecteds solve to y = x up to rounding noise; say so.
            noise = 1e-9 * (max(abs(value) for value in y_values) or 1.0)
            intercept = 0.0 if abs(intercept) < noise else intercept
            slope = 1.0 if abs(slope - 1.0) < 1e-9 else slope
            trend_y = slope * trend_x + intercept
            text = (
                f"{y_name} = {slope:.4g} × {x_name} {intercept:+.4g}  "
                f"(R² {r_squared:.3f})"
            )
        else:
            # The fits seed from the series' ends, so it goes in x order.
            order = np.argsort(x_values)
            fit = fit_series(
                np.asarray(x_values)[order], np.asarray(y_values)[order], method
            )

            if fit is None:
                self._fit_artists.append(
                    self._axes.text(
                        EQUATION_BOX_X,
                        EQUATION_BOX_TOP_Y,
                        f"Too few points for a {FIT_LABELS[method].lower()} trend",
                        transform=self._axes.transAxes,
                        va="top",
                        fontsize="x-small",
                        color="gray",
                    )
                )

                return

            trend_x = np.linspace(min(x_values), max(x_values), FIT_CURVE_SAMPLES)
            trend_y = fit.predict(trend_x)
            # The fit's own text reads "y = f(t)"; name the axes instead.
            equation = re.sub(r"\bt\b", x_name, fit.equation.removeprefix("y = "))
            text = f"{y_name} = {equation}  (R² {fit.r_squared:.3f})"

        (trend_line,) = self._axes.plot(
            trend_x,
            trend_y,
            linestyle="--",
            color="black",
            alpha=0.7,
            label="_nolegend_",
        )
        self._fit_artists.append(trend_line)
        self._fit_artists.append(
            self._axes.text(
                EQUATION_BOX_X,
                EQUATION_BOX_TOP_Y,
                text,
                transform=self._axes.transAxes,
                va="top",
                fontsize="x-small",
            )
        )

    def _shade_trimmed_tails(self, trim_edges):
        """Grey band over the tail the poor-fit trim kept out of at
        least one ROI's fit, so the curves drawn across it read as the
        extrapolation they are. ``trim_edges`` is (fitted_end,
        series_end) per fitted ROI."""
        dropped = [edge for edge in trim_edges if edge[0] < edge[1]]
        if not dropped:
            return
        self._fit_artists.append(
            self._axes.axvspan(
                min(fitted_end for fitted_end, _ in dropped),
                max(series_end for _, series_end in dropped),
                color="gray",
                alpha=TRIM_SHADE_ALPHA,
                zorder=0,
            )
        )

    def _apply_legend(self, wanted):
        if wanted:
            self._axes.legend(loc="best", fontsize="small")
        elif self._axes.get_legend() is not None:
            self._axes.get_legend().remove()

    def _note_hidden_points(self, series, log_x, log_y):
        """Matplotlib drops non-positive values on a log axis without a
        word, and two cases are certain rather than hypothetical:
        elapsed time starts at 0, and a normalised curve's minimum is
        exactly 0. Count them instead of letting data vanish."""
        if not (log_x or log_y):
            return
        hidden = 0
        for _name, elapsed, values in series.values():
            for time, value in zip(elapsed, values):
                if value != value:
                    continue  # already a gap, not a casualty
                if (log_x and time <= 0) or (log_y and value <= 0):
                    hidden += 1
        if not hidden:
            return
        self._fit_artists.append(
            self._axes.text(
                0.5,
                NOTE_HIDDEN_Y,
                f"Log axis hides {hidden} non-positive "
                f"{'point' if hidden == 1 else 'points'}",
                transform=self._axes.transAxes,
                ha="center",
                va="bottom",
                color="gray",
                fontsize="x-small",
            )
        )

    def _note_dropped_outliers(self):
        """Say how many points the outlier test removed.

        A removal leaves the same gap a missing measurement does, and
        the two mean opposite things — one is data the app never had,
        the other is data it decided to ignore. Counting them is the
        cheapest way to keep that decision visible; the CSV carries
        which ones, per point.

        A count rather than a mark on each: the value that was dropped
        belongs to the raw series, and by here the curve has been
        baseline-shifted or normalised, so there is no honest y to draw
        it at."""
        dropped = sum(
            sum(1 for flag in flags if flag) for flags in self._outliers.values()
        )
        if not dropped:
            return
        self._fit_artists.append(
            self._axes.text(
                0.5,
                NOTE_OUTLIERS_Y,
                f"{dropped} {'point' if dropped == 1 else 'points'} "
                f"dropped as outliers",
                transform=self._axes.transAxes,
                ha="center",
                va="bottom",
                color="gray",
                fontsize="x-small",
            )
        )

    def _note_missing_temperatures(self, series, figure_settings):
        """Count the frames the heater log does not cover (NaN x on a
        temperature axis) — they cannot be drawn anywhere honest, so
        they are counted instead of silently vanishing. Frames, not
        points: every ROI shares the same x, and multiplying the count
        by the ROIs would overstate what is missing. The coverage line
        under the count says where the logs were looked for, so a gap
        reads as a misfiled log rather than a broken join."""
        if figure_settings.x_axis != "temperature":
            return

        session = self._model.session
        frames = next((elapsed for _name, elapsed, _values in series.values()), [])
        note = heater_coverage_note(
            sum(1 for x in frames if x != x),
            session.heater_log_coverage,
            bool(session.heater_log_fallback_dir),
        )

        if not note:
            return

        self._fit_artists.append(
            self._axes.text(
                0.5,
                NOTE_NO_TEMP_Y,
                note,
                transform=self._axes.transAxes,
                ha="center",
                va="bottom",
                color="gray",
                fontsize="x-small",
            )
        )

    def _draw_hint(self, message):
        self._fit_artists.append(
            self._axes.text(
                0.5,
                0.5,
                message,
                transform=self._axes.transAxes,
                ha="center",
                va="center",
                color="gray",
            )
        )

    def _draw_fits(self, series, figure_settings):
        """Dashed fit overlay + optional corner equation lines per ROI;
        series that cannot be fitted are silently skipped (the popup
        table is where failures are reported). Returns the (fitted_end,
        series_end) pairs the trim shading is drawn from."""
        equation_lines, trim_edges = [], []
        _quantity, x_unit = x_quantity(figure_settings)

        for roi, name, fit, finite_t in self._fitted_rois(series, figure_settings):
            trim_edges.append((fit.fitted_end, finite_t.max()))
            dense = np.linspace(finite_t.min(), finite_t.max(), FIT_CURVE_SAMPLES)
            (overlay,) = self._axes.plot(
                dense,
                fit.predict(dense),
                linestyle="--",
                alpha=0.8 * roi.style.plot_alpha,
                color=roi.style.color,
                label="_nolegend_",
            )
            self._fit_artists.append(overlay)
            equation_lines.append(
                (
                    roi.style.color,
                    roi.style.plot_alpha,
                    f"{name}: {fit.equation} (R²={fit.r_squared:.3f})"
                    f"{trimmed_note(fit, finite_t.max(), unit=x_unit)}",
                )
            )
            self._draw_extrema(
                fit,
                finite_t.min(),
                finite_t.max(),
                roi,
                figure_settings,
                marker_y=fit.predict,
            )
        if figure_settings.show_fit_equations:
            for index, (color, alpha, text) in enumerate(equation_lines):
                self._fit_artists.append(
                    self._axes.text(
                        EQUATION_BOX_X,
                        EQUATION_BOX_TOP_Y - EQUATION_LINE_STEP_Y * index,
                        text,
                        transform=self._axes.transAxes,
                        va="top",
                        fontsize="x-small",
                        color=color,
                        alpha=alpha,
                    )
                )
        return trim_edges

    def _draw_extrema(
        self,
        fit,
        t_start,
        t_end,
        roi,
        figure_settings,
        marker_y,
        with_second_derivative_extrema=True,
    ):
        """Point (plus optional v/h line and coordinates) on
        ``marker_y`` (a function of t: the curve or one of its
        derivatives) at each enabled marker's t — where the fitted
        curve's second derivative peaks/troughs, and where the curve
        changes fastest. ``with_second_derivative_extrema`` False
        leaves the d² ones out."""
        wanted = [
            key
            for key, enabled in (
                ("max", figure_settings.show_second_derivative_max),
                ("min", figure_settings.show_second_derivative_min),
            )
            if enabled and with_second_derivative_extrema
        ]
        times = []

        if wanted:
            extrema = second_derivative_extrema(fit, t_start, t_end)
            times.extend(extrema[key][0] for key in wanted if key in extrema)

        if figure_settings.show_second_derivative_zero:
            t_star = fastest_change_time(fit, t_start, t_end)

            if t_star is not None:
                times.append(t_star)

        for t_star in times:
            self._draw_extremum_marker(
                t_star, float(marker_y(t_star)), roi, figure_settings
            )

    def _draw_extremum_marker(self, t_star, y_star, roi, figure_settings):
        """One marker at (t_star, y_star) — on the fitted curve in the
        intensity view, on the derivative's curve in a derivative view."""
        alpha = roi.style.plot_alpha
        (point,) = self._axes.plot(
            [t_star],
            [y_star],
            marker="o",
            linestyle="",
            alpha=alpha,
            color=roi.style.color,
            markeredgecolor="black",
            label="_nolegend_",
        )
        self._fit_artists.append(point)
        if figure_settings.second_derivative_vline:
            self._fit_artists.append(
                self._axes.axvline(
                    t_star, color=roi.style.color, linestyle=":", alpha=0.6 * alpha
                )
            )
        if figure_settings.second_derivative_hline:
            self._fit_artists.append(
                self._axes.axhline(
                    y_star, color=roi.style.color, linestyle=":", alpha=0.6 * alpha
                )
            )
        if figure_settings.second_derivative_coords:
            self._fit_artists.append(
                self._axes.annotate(
                    f"({t_star:.3g}, {y_star:.3g})",
                    (t_star, y_star),
                    textcoords="offset points",
                    xytext=(6, 6),
                    fontsize="x-small",
                    color=roi.style.color,
                    alpha=alpha,
                )
            )


class _PlotToolbar(NavigationToolbar2QT):
    """The standard navigation toolbar, with Home also releasing the
    view the user zoomed or panned into — otherwise the next redraw
    would restore what Home just cleared."""

    def home(self, *args):
        self.canvas.release_view()
        super().home(*args)


def _save_figure(canvas):
    """Render the current figure at the session's export settings; the
    dialog defaults into the experiment's analysis folder."""
    session = roi_analysis_model.session
    default_dir = (
        str(analysis_directory(session.directory)) if session.directory else ""
    )
    extension = session.figure.export_format
    dialog = FileDialog(
        action="save as",
        default_directory=default_dir,
        default_filename=f"roi_intensities.{extension}",
        wildcard=f"*.{extension}",
    )
    if dialog.open() != OK:
        return
    canvas.figure.savefig(dialog.path, dpi=session.figure.export_dpi, format=extension)


class RoiPlotDockPane(DockPane):
    """ROI intensity vs time for the filtered image series."""

    id = PKG + ".roi_plot_dock_pane"
    name = "ROI Intensities"

    canvas = Instance(RoiPlotCanvas)
    table = Instance(RoiStatsTable)
    _controls_ui = Any()
    _controls_scroll = Any()
    #: The Expected tab tables' copy / paste event filters, one per
    #: table, replaced with the controls on every rebuild.
    _table_clipboard_filters = List()
    _equations_ui = Any()

    def create_contents(self, parent):
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        self.canvas = RoiPlotCanvas(roi_analysis_model)
        self.canvas.setMinimumSize(
            ROI_PLOT_CANVAS_MIN_WIDTH, ROI_PLOT_CANVAS_MIN_HEIGHT
        )
        layout.addWidget(_PlotToolbar(self.canvas, widget))
        self._controls_ui = self._build_controls(widget)
        # The controls get their own scroll area so a narrow pane
        # scrolls them instead of forcing the whole pane wide, and a
        # short pane scrolls them instead of squeezing the plot away.
        self._controls_scroll = QScrollArea(widget)
        self._controls_scroll.setWidgetResizable(True)
        self._controls_scroll.setWidget(self._controls_ui.control)
        # All three sections share one splitter, so the controls are as
        # draggable as the chart and the table: a fixed cap on them
        # decided for the user how much of the pane the buttons were
        # worth, and they scroll inside whatever height they are given.
        splitter = QSplitter(Qt.Orientation.Vertical, widget)
        splitter.addWidget(self._controls_scroll)
        splitter.addWidget(self.canvas)
        self.table = RoiStatsTable(roi_analysis_model, splitter)
        splitter.addWidget(self.table)
        # Nothing collapses to nothing by dragging: a section dragged
        # shut is hard to find again.
        splitter.setChildrenCollapsible(False)
        self._controls_scroll.setMinimumHeight(ROI_PLOT_SECTION_MIN_PX)
        self.table.setMinimumHeight(ROI_PLOT_SECTION_MIN_PX)
        splitter.setStretchFactor(0, 0)  # controls keep their size
        splitter.setStretchFactor(1, 3)  # the chart takes the room
        splitter.setStretchFactor(2, 1)
        splitter.setSizes(
            [
                ROI_PLOT_CONTROLS_MAX_HEIGHT,
                3 * ROI_PLOT_CONTROLS_MAX_HEIGHT,
                ROI_PLOT_CONTROLS_MAX_HEIGHT,
            ]
        )
        layout.addWidget(splitter, 1)
        # No progress label here: the image viewer pane already shows
        # roi_analysis.progress_text, and one status belongs in one
        # place.
        roi_analysis_model.observe(self._on_session_swapped, "session")
        roi_analysis_model.observe(self._on_save_plot, "save_plot_button")
        roi_analysis_model.observe(self._on_fit_equations, "fit_equations_button")
        roi_analysis_model.observe(self._on_heater_dir, "heater_dir_button")
        # The pane may be resized below the content's minimum; past that
        # point scrollbars take over instead of the dock pane locking.
        scroll = QScrollArea(parent)
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _build_controls(self, parent):
        session = roi_analysis_model.session
        ui = _plot_controls_view.ui(
            context={
                # TableEditor cell editors copy the context's "object"
                # and fail without one, leaving the Expected table
                # uneditable; the model stands in for it.
                "object": roi_analysis_model,
                "session": session,
                "figure": session.figure,
                "model": roi_analysis_model,
            },
            kind="subpanel",
            parent=parent,
        )

        self._table_clipboard_filters = [
            install_table_clipboard(editor)
            for name in ("expected_rows", "custom_points")
            for editor in ui.get_editors(name)
        ]

        return ui

    @observe("visible")
    def _mirror_visibility(self, event):
        roi_analysis_model.plot_visible = event.new

    def _on_session_swapped(self, event):
        old_ui = self._controls_ui
        self._controls_ui = self._build_controls(self._controls_scroll)
        # takeWidget before setWidget: setWidget destroys the control it
        # replaces, and TraitsUI still has to dispose of that one.
        self._controls_scroll.takeWidget()
        self._controls_scroll.setWidget(self._controls_ui.control)
        old_ui.dispose()

    def _on_save_plot(self, event):
        _save_figure(self.canvas)

    def _on_heater_dir(self, event):
        session = roi_analysis_model.session
        default = session.heater_log_dir or (
            str(Path(session.directory) / HEATER_LOGS_DIR_NAME)
            if session.directory
            else ""
        )
        dialog = DirectoryDialog(default_path=default)
        if dialog.open() == OK:
            session.heater_log_dir = dialog.path

    def _on_fit_equations(self, event):
        if self._equations_ui is not None and self._equations_ui.control is not None:
            self._equations_ui.info.object.reload()
            self._equations_ui.control.raise_()
            self._equations_ui.control.activateWindow()
            return
        table = FitEquationsTable(
            session=roi_analysis_model.session,
            model=roi_analysis_model,
            filtered_paths=list(roi_analysis_model.filtered_paths),
        )
        table.reload()
        self._equations_ui = table.edit_traits(kind="live")

    def destroy(self):
        # Everything below was registered in create_contents, which a
        # constructed-but-never-shown pane never ran (pyface's own
        # destroy() guards its teardown the same way).
        if self.control is not None:
            roi_analysis_model.plot_visible = False
            self.canvas.detach()
            self.table.detach()
            self._controls_ui.dispose()
            if (
                self._equations_ui is not None
                and self._equations_ui.control is not None
            ):
                self._equations_ui.dispose()
            roi_analysis_model.observe(self._on_session_swapped, "session", remove=True)
            roi_analysis_model.observe(
                self._on_save_plot, "save_plot_button", remove=True
            )
            roi_analysis_model.observe(
                self._on_fit_equations, "fit_equations_button", remove=True
            )
            roi_analysis_model.observe(
                self._on_heater_dir, "heater_dir_button", remove=True
            )
        super().destroy()

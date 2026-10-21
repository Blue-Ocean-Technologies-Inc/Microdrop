# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free ROI analysis state: the ROI definitions (shared base geometry
plus forward drift-overrides), the intensity-stats cache, and batch
progress. Mutated only on the GUI thread (button events and the dock
pane's drain timer), so no Qt bridging is needed."""

# Standard library imports.
import math
import re
import uuid
from pathlib import Path

# Enthought library imports.
from pyface.undo.api import CommandStack, UndoManager
from traits.api import (
    Bool,
    Button,
    DelegatesTo,
    Dict,
    Enum,
    Event,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Range,
    Str,
    Tuple,
    cached_property,
    observe,
)

# Microdrop utils imports.
from microdrop_utils.expression import function_error

# Local imports.
from ..discovery import capture_timestamp
from ..scale_bar import DEFAULT_UNIT, UNITS
from .consts import (
    AI_DRIFT_CHECK_INTERVAL_DEFAULT,
    AI_MAX_SIZE_DEFAULT_PX,
    AI_MIN_SIZE_DEFAULT_PX,
    AI_SIGNIFICANCE_DEFAULT,
    AI_SIZE_FILTER_CEILING_PX,
    BUTTER_CUTOFF,
    BUTTER_CUTOFF_BOUNDS,
    BUTTER_ORDER,
    BUTTER_ORDER_BOUNDS,
    COPY_TREND_CALIBRATED,
    COPY_TREND_FLIPPED,
    COPY_TREND_NO_TREND,
    COPY_TREND_NOT_TEMPERATURE,
    COPY_TREND_TOOLTIP,
    EXPECTED_METRIC_LABELS,
    EXPECTED_METRICS,
    HEATER_SENSOR_MEAN,
    HEATER_WINDOW_BOUNDS_MS,
    HEATER_WINDOW_MS,
    OUTLIER_THRESHOLD_BOUNDS_MAD,
    OUTLIER_THRESHOLD_MAD,
    OUTLIER_WINDOW_BOUNDS_PTS,
    OUTLIER_WINDOW_PTS,
    RING_GAP_BOUNDS_PX,
    RING_GAP_PX,
    RING_THICKNESS_BOUNDS_PX,
    RING_THICKNESS_PX,
    ROI_ALPHA_BOUNDS_PCT,
    ROLLING_BALL_RADIUS_BOUNDS_PX,
    ROLLING_BALL_RADIUS_PX,
    SAVGOL_ORDER,
    SAVGOL_ORDER_BOUNDS,
    SAVGOL_WINDOW_BOUNDS_PTS,
    SAVGOL_WINDOW_PTS,
    SHAPE_STATS,
    TIME_UNITS,
    VIEW_HOLDING_MODES,
    VIEW_MODE_LABELS_BY_X_AXIS,
    VIEW_MODES,
    X_AXIS_MODES,
)
from .curve_fit import FIT_METHODS, TREND_METHODS, FitResult
from .fit_presets import choices_for
from .perspective import perspective_matrix
from .plot_series import SMOOTH_METHODS, is_calibrated, trend_fit, trend_points
from .sam_detect import Candidate

#: The Roi trait holding the user's expected value of each
#: EXPECTED_METRICS landmark. The zero crossing's keeps its original
#: name: it is persisted under it.
EXPECTED_TRAITS = {
    "zero": "expected_fastest_change",
    "max": "expected_second_derivative_max",
    "min": "expected_second_derivative_min",
}

#: Matches the "<prefix> N" names next_roi_name() itself produces, to
#: find the next free number; formatted with the escaped prefix.
ROI_NAME_PATTERN = r"^{prefix} (\d+)$"

#: Stats the plot can show. "bg_corrected" is interior mean minus the
#: outline-ring mean — the usual fluorescence background correction
#: the ring exists for. The next four are size-aware: "integrated" is
#: the ROI's total signal, and "per_area" its density — which is the
#: mean times a constant, since the pixel counts cancel (see the
#: area-statistics design note). "area" is the ROI's own size, in
#: the calibrated unit.
#: The area-normalised pair takes out what a shrinking droplet does to
#: the mean: evaporation keeps the fluorophore count N while the area
#: A shrinks, so the mean (∝ N/A) rises though the integrated signal
#: (mean × A ∝ N) stays flat — and per area (∝ N/A²) would only make
#: it worse. Dividing the integrated signal by the ROI's area on the
#: first analysed image instead, integrated / A_ref, keeps intensity
#: units, equals the mean on that first image, and plots flat under
#: pure concentration. The droplet-shape quantities close the list.
PLOT_STATS = (
    "mean",
    "bg_corrected",
    "median",
    "min",
    "max",
    "outline_mean",
    "integrated",
    "bg_integrated",
    "per_area",
    "bg_per_area",
    "area_normalized",
    "bg_area_normalized",
    "area",
) + SHAPE_STATS


class RoiStyle(HasTraits):
    """Plot styling for one ROI's line (persisted per experiment)."""

    color = Str("#1f77b4")
    line_style = Enum("solid", "dashed", "dotted", "dashdot")
    marker = Enum("none", ".", "o", "s", "^", "x")
    marker_size = Float(4.0)

    #: Whether this ROI is drawn on the figure at all, and how opaque —
    #: the device viewer's eye/alpha pair, as a percentage. Both are
    #: display-only: a hidden ROI is still computed, still listed in the
    #: stats table, and still exported to CSV. The one exception is a
    #: negative mask's eye: a hidden mask is not subtracted (see
    #: AnalysisSession.negatives_for). Range needs the explicit
    #: default, or it would start every ROI fully transparent.
    visible = Bool(True)
    alpha = Range(*ROI_ALPHA_BOUNDS_PCT, ROI_ALPHA_BOUNDS_PCT[1], mode="spinner")

    @property
    def plot_alpha(self):
        """``alpha`` as the 0-1 fraction matplotlib wants."""
        return self.alpha / 100.0


class FigureSettings(HasTraits):
    """Figure-level plot settings (axis limits and export defaults)."""

    x_auto = Bool(True)
    x_min = Float(0.0)
    x_max = Float(1.0)
    y_auto = Bool(True)
    y_min = Float(0.0)
    y_max = Float(1.0)
    export_format = Enum("png", "svg", "pdf", "tiff")
    export_dpi = Enum(300, 150, 600)
    #: Which fit the plot draws: a built-in key, "preset:<name>" for a
    #: saved equation, or "custom" while one is typed but unsaved. A
    #: Str rather than an Enum because the saved equations are not
    #: known at import time; an unresolvable key fits nothing.
    fit_method = Str(FIT_METHODS[0])

    #: The equation being fitted while fit_method is "custom", kept per
    #: experiment so reopening one reproduces its fit whether or not
    #: the equation was ever saved as a preset.
    custom_expression = Str()

    #: {parameter: starting value} for the typed equation. Empty means
    #: seed it automatically; a complete set steers the optimizer where
    #: the automatic seeds land somewhere useless.
    initial_guesses = Dict(Str, Float)
    #: Refit on a shorter leading slice when R² is poor, for series
    #: whose tail the model does not describe (a bleached plateau).
    trim_poor_fit = Bool(False)
    #: Display scales (the data and the fits are untouched) and the
    #: 0-100% per-ROI normalisation (which rewrites the values).
    log_x = Bool(False)
    log_y = Bool(False)
    normalize = Bool(False)
    #: Drop points that fail the Hampel test — a rolling median and
    #: MAD — before anything is fitted or drawn. They are marked on
    #: the plot and flagged in the CSV rather than vanishing.
    remove_outliers = Bool(False)
    outlier_threshold = Range(*OUTLIER_THRESHOLD_BOUNDS_MAD, OUTLIER_THRESHOLD_MAD)
    outlier_window = Range(
        *OUTLIER_WINDOW_BOUNDS_PTS, OUTLIER_WINDOW_PTS, mode="spinner"
    )
    #: Draw each line straight across its missing points (dropped
    #: outliers, uncomputed images) instead of breaking it. Display
    #: only — the fits and the CSV keep the gaps.
    interpolate_gaps = Bool(True)
    #: Draw the excluded images' points as faint hollow markers that
    #: a click brings back into the analysis. Display only: they are
    #: never fitted, and never move the axes either way.
    show_excluded_points = Bool(True)

    #: Display-only smoothing of the drawn curves. The fits keep the
    #: unsmoothed points: neighbouring values in a smoothed curve are
    #: no longer independent, which flatters R² and shrinks the
    #: parameter uncertainties for the wrong reason.
    smooth_method = Enum(*SMOOTH_METHODS)
    savgol_window = Range(*SAVGOL_WINDOW_BOUNDS_PTS, SAVGOL_WINDOW_PTS, mode="spinner")
    savgol_order = Range(*SAVGOL_ORDER_BOUNDS, SAVGOL_ORDER, mode="spinner")
    butter_order = Range(*BUTTER_ORDER_BOUNDS, BUTTER_ORDER, mode="spinner")
    #: Cutoff as a fraction of the Nyquist frequency: 1.0 passes
    #: everything, small values keep only the slowest changes. A
    #: fraction rather than Hz because a burst-captured series is not
    #: evenly spaced in time, and only the point spacing is knowable.
    butter_cutoff = Range(*BUTTER_CUTOFF_BOUNDS, BUTTER_CUTOFF)

    #: Each curve less its own first value: change from baseline.
    subtract_first = Bool(False)
    #: Subtract the mean of the ROIs marked as background references,
    #: per image. Stacks with the ring correction and subtract_first.
    subtract_background_ref = Bool(False)
    show_legend = Bool(True)
    #: Corner box with each ROI's fitted equation.
    show_fit_equations = Bool(False)
    #: Mark where the fitted curve's second derivative peaks/troughs.
    show_second_derivative_max = Bool(False)
    show_second_derivative_min = Bool(False)
    #: Mark where the fitted curve's second derivative crosses zero — the
    #: peak of |dy/dx|, the fastest change, which the Fastest change view
    #: and the Expected tab report.
    show_second_derivative_zero = Bool(False)
    #: Marker dressing for the enabled markers.
    second_derivative_vline = Bool(True)
    second_derivative_hline = Bool(False)
    second_derivative_coords = Bool(True)
    #: Which chart the plot pane renders.
    view_mode = Enum(*VIEW_MODES)
    #: Plot expected against actual instead of actual against expected,
    #: so the trend reads expected = slope × actual + intercept.
    flip_actual_expected = Bool(False)

    #: Also compare where the fitted curve's second derivative peaks /
    #: troughs against the user's expected value: a row per ROI in the
    #: Expected table, a point per ROI in the Actual vs expected view.
    compare_second_derivative_max = Bool(False)
    compare_second_derivative_min = Bool(False)

    #: The EXPECTED_METRICS landmarks compared: the zero crossing
    #: always, plus the extrema switched on above, in that order.
    compared_metrics = Property(
        List(Str),
        observe="compare_second_derivative_max, compare_second_derivative_min",
    )

    #: Which fit the Actual vs expected view's trend line uses.
    trend_method = Enum(*TREND_METHODS)

    #: What the curves are plotted against: elapsed capture time, the
    #: heater log's temperature at each capture, the protocol step it
    #: was taken in, or its frame number. The swap happens in
    #: derive_series, so the fits follow it — a melt curve's midpoint
    #: comes out as a °C rather than a second.
    x_axis = Enum(*X_AXIS_MODES)
    #: The time axis's unit, applied in derive_series so the fits and
    #: their landmarks read in it too. The heater join and the CSV's
    #: elapsed_sec stay in seconds.
    time_unit = Enum(*TIME_UNITS)
    #: Which thermistor the temperature axis reads; "mean" averages
    #: every sensor on each log line.
    heater_sensor = Str(HEATER_SENSOR_MEAN)
    #: How generous the time join is (ms): a capture's temperature is
    #: the mean of every heater sample within ±window/2 of it. 0 means
    #: exact — linear interpolation at the capture instant.
    heater_window_ms = Range(*HEATER_WINDOW_BOUNDS_MS, HEATER_WINDOW_MS, mode="spinner")
    #: actual = f(expected) — the same expression as the heater's
    #: compensation; the log's temperature is mapped back to expected
    #: by inverting it numerically.
    temperature_expression = Str("x")
    #: Why temperature_expression does not parse, "" when it does (or
    #: is the identity). Never persisted.
    temperature_expression_error = Property(Str, observe="temperature_expression")

    #: Which of the Fit tab's groups are open — display state, but
    #: persisted so the panel reopens the way it was left.
    show_method_group = Bool(True)
    show_metrics_group = Bool(True)
    #: Whether the Expected tab's Custom points group is open, persisted
    #: the same way.
    show_custom_points_group = Bool(True)

    def _get_compared_metrics(self):
        enabled = {
            "zero": True,
            "max": self.compare_second_derivative_max,
            "min": self.compare_second_derivative_min,
        }

        return [metric for metric in EXPECTED_METRICS if enabled[metric]]

    def _get_temperature_expression_error(self):
        return function_error(self.temperature_expression)


class ScaleCalibration(HasTraits):
    """Image scale for the on-canvas bar and the area readouts
    (persisted per experiment). It never changes which pixels are
    measured, only the units the Area and Per area values are
    reported in."""

    #: Metres one image pixel spans; 0.0 means not calibrated.
    metres_per_pixel = Float(0.0)
    #: What the user typed, kept for the readout and for re-editing.
    value = Float(0.0)
    #: Enum's first argument is the default, so mm wins over m.
    unit = Enum(DEFAULT_UNIT, UNITS)

    def calibrated(self):
        return self.metres_per_pixel > 0.0


class RollingBall(HasTraits):
    """Rolling-ball flattening applied to the whole frame before any
    ROI is measured (persisted per experiment). Like the ring, this
    changes what is measured, so it is part of the stats cache key.

    The radius is the scale of the unevenness to remove: it must be
    comfortably larger than the features being measured, or the ball
    rolls over them and takes the signal with the background."""

    enabled = Bool(False)
    radius_px = Range(
        *ROLLING_BALL_RADIUS_BOUNDS_PX, ROLLING_BALL_RADIUS_PX, mode="spinner"
    )

    #: Draw the ball on the image at its true size, as a guide for
    #: choosing the radius by eye. Display only — it is measured with
    #: whether or not it is shown.
    show_reference = Bool(False)

    def effective_radius(self):
        """The radius to correct with, or 0 when it is switched off —
        what compute_image_stats takes."""
        return self.radius_px if self.enabled else 0


class PerspectiveCorrection(HasTraits):
    """A 4-point perspective transform applied to every frame before it is
    shown or measured (persisted per experiment). Defined like the device
    viewer's camera alignment: ``source_quad`` are the four points picked
    on the raw frame, ``target_quad`` where they were dragged to — both in
    image pixels. Only while ``enabled`` does it change what is measured,
    so the effective matrix is part of the stats cache key."""

    #: Points picked on the raw frame ([] until defined).
    source_quad = List(Tuple(Float, Float))

    #: Where those points land after the warp.
    target_quad = List(Tuple(Float, Float))

    #: Apply the transform (the toolbar's on/off toggle).
    enabled = Bool(False)

    #: The flattened homography source -> target, () when undefined.
    matrix = Property(Tuple, observe="source_quad.items, target_quad.items")

    @cached_property
    def _get_matrix(self):
        return perspective_matrix(self.source_quad, self.target_quad)

    def is_defined(self):
        return bool(self.matrix)

    def effective_matrix(self):
        """The matrix to warp with, or () when it is switched off or not
        defined — what compute_image_stats takes."""
        return self.matrix if self.enabled else ()


class BackgroundRing(HasTraits):
    """The annulus each ROI's background is read from (persisted per
    experiment). These change what is measured, so they are part of the
    stats cache key."""

    #: Pixels between the ROI's edge and the ring — fluorescence bleeds
    #: past the boundary and that halo is not background.
    gap_px = Range(*RING_GAP_BOUNDS_PX, RING_GAP_PX, mode="spinner")
    thickness_px = Range(*RING_THICKNESS_BOUNDS_PX, RING_THICKNESS_PX, mode="spinner")
    show_on_canvas = Bool(True)


class Roi(HasTraits):
    """One region of interest: a shared base geometry applying everywhere,
    plus optional overrides anchored at capture times that apply from
    their anchor forward (drift compensation)."""

    #: Stable identity used in cache keys and result columns.
    roi_id = Str()

    #: Display name (also the CSV column prefix and plot legend label).
    name = Str()

    #: Shape, with the geometry lists roi_geometry defines: ellipse
    #: [cx, cy, rx, ry, angle], box [x, y, width, height, angle] with
    #: (x, y) the unrotated top-left corner, capsule [cx, cy,
    #: half_length, radius, angle], polygon [x1, y1, x2, y2, ...] (a
    #: contour's vertex list, with any rotation already applied to the
    #: coordinates). All values are image-pixel floats bar the angle,
    #: which is degrees clockwise.
    kind = Enum("ellipse", "box", "capsule", "polygon")

    #: Base geometry, applying to every image without a later override.
    geometry = List(Float)

    #: Capture time of the image the ROI was created on — edits at or
    #: before it update the base instead of adding an override. For a
    #: negative mask it is also where the mask starts (see applies_at);
    #: 0.0 (no image shown at creation) means from the first image.
    base_anchor = Float(0.0)

    #: anchor capture time -> geometry; an override applies from its
    #: anchor forward until the next override.
    overrides = Dict(Float, List)

    #: Plot styling (line color/style/marker); persisted with the ROI.
    style = Instance(RoiStyle, ())

    #: A region that should hold no signal, used as a background
    #: reference: the marked ROIs' mean is subtracted from every ROI
    #: when that correction is on (see
    #: background_ref_corrected_series).
    is_background_ref = Bool(False)

    #: The x value the user expects this ROI's fastest change at, for
    #: the actual-vs-expected view. NaN means not set — use the actual
    #: value — so by default every point sits on the identity line.
    expected_fastest_change = Float(math.nan)

    #: The same for where the fitted curve's second derivative peaks /
    #: troughs, compared when the Expected tab's d² max / min are on.
    expected_second_derivative_max = Float(math.nan)
    expected_second_derivative_min = Float(math.nan)

    #: A negative mask rather than a measured region: its interior is
    #: subtracted from every positive ROI it overlaps (and from their
    #: background rings). It has no stats of its own and is never a
    #: background reference. Hiding it with its eye (``style.visible``)
    #: leaves it out of the calculation as well as the canvas. It is in
    #: force only from its base_anchor image onward (see applies_at).
    is_negative = Bool(False)

    def _roi_id_default(self):
        return uuid.uuid4().hex[:8]

    def expected_or(self, metric, actual):
        """The expected value of the ``metric`` landmark (an
        EXPECTED_METRICS key), or ``actual`` while unset."""
        expected = getattr(self, EXPECTED_TRAITS[metric])

        return actual if math.isnan(expected) else expected

    def set_expected(self, metric, value):
        """Set the expected value of the ``metric`` landmark."""
        setattr(self, EXPECTED_TRAITS[metric], value)

    def applies_at(self, capture_time):
        """Whether this ROI is in force on an image captured at
        ``capture_time``. A positive ROI always applies; a negative mask
        applies from the image it was drawn on (its base_anchor) onward,
        and on earlier images is neither drawn nor subtracted. A mask
        created with no image shown has a 0.0 anchor, so applies to
        every image."""
        return not self.is_negative or capture_time >= self.base_anchor

    def effective_geometry(self, capture_time):
        """The geometry in force for an image captured at
        ``capture_time``: the override with the greatest anchor at or
        before it, else the base geometry."""
        anchors = [anchor for anchor in self.overrides if anchor <= capture_time]
        if anchors:
            return list(self.overrides[max(anchors)])
        return list(self.geometry)

    def apply_edit(self, capture_time, geometry):
        """Record an edit made while viewing the image captured at
        ``capture_time``: at or before the base anchor it updates the
        base, later it upserts a forward override."""
        if capture_time <= self.base_anchor:
            self.geometry = list(geometry)
        else:
            self.overrides[capture_time] = list(geometry)

    def clear_overrides(self):
        self.overrides = {}


class ExpectedRow(HasTraits):
    """One ROI landmark's line in the Expected table: the x value the
    fitted curve puts it at beside the one the user expects."""

    #: The ROI the row reads its name from and writes its expected to.
    roi = Instance(Roi)

    #: The ROI's display name.
    name = DelegatesTo("roi")

    #: Which fitted-curve landmark the row compares.
    metric = Enum(*EXPECTED_METRICS)

    #: The landmark's table label.
    label = Property(Str, observe="metric")

    #: The landmark's x value on the fitted curve; NaN when unknown.
    actual = Float(math.nan)

    #: The user's expected value — the actual while none is set.
    expected = Property(
        Float,
        observe="roi.expected_fastest_change, "
        "roi.expected_second_derivative_max, "
        "roi.expected_second_derivative_min, actual",
    )

    def _get_label(self):
        return EXPECTED_METRIC_LABELS[self.metric]

    def _get_expected(self):
        return self.roi.expected_or(self.metric, self.actual)

    def _set_expected(self, value):
        self.roi.set_expected(self.metric, value)


class CustomPoint(HasTraits):
    """An (actual, expected) pair the user types in rather than one a
    ROI's fit produced — a standard of known value measured elsewhere,
    say — plotted and fitted with the ROI points in the Actual vs
    expected view."""

    #: The point's label on the plot and in the CSV.
    name = Str()

    #: The measured and the expected x value; NaN until typed.
    actual = Float(math.nan)
    expected = Float(math.nan)


class AnalysisSession(HasTraits):
    """Everything belonging to one experiment's analysis, swapped
    wholesale when the browsed experiment changes: the ROI set, the
    computed-stats store, and the plot configuration."""

    #: Experiment directory this session was loaded from ('' = none).
    directory = Str()

    rois = List(Instance(Roi))

    #: The measured ROIs — every consumer that lists, plots or exports
    #: ROIs reads this rather than ``rois``.
    positive_rois = Property(List(Instance(Roi)), observe="rois.items.is_negative")

    #: The negative masks, subtracted from the positives they overlap.
    negative_rois = Property(List(Instance(Roi)), observe="rois.items.is_negative")

    #: Filenames the user excluded from analysis: skipped by the stats
    #: batch, plot series, CSV export, and the drift tracker, while
    #: viewing and ROI drawing on them stay untouched. Filenames, not
    #: paths, so an experiment folder can move without unmarking them.
    excluded_images = List(Str)

    def is_excluded(self, path):
        """Whether analysis skips the image at ``path``."""
        return Path(path).name in self.excluded_images

    #: (path str, mtime, roi_id, kind, geometry tuple) -> stats dict.
    #: The geometry in the key makes invalidation implicit: an edit only
    #: misses on the images its override actually covers.
    stats = Dict()

    #: Bumped after every drain absorption and after a store load — Dict
    #: item writes don't notify, so observers watch this instead.
    stats_revision = Int(0)  # TODO: convert to Event trait

    #: Which stat the plot shows.
    plot_stat = Enum(*PLOT_STATS)

    #: Folder of the heater's JSONL logs, persisted per experiment.
    #: Empty means "not resolved yet"; the controller fills in the
    #: experiment's own heater_logs folder as the default.
    heater_log_dir = Str()

    #: The sibling experiment's heater_logs folder the samples came
    #: from when the default heater_log_dir covers none of the captures
    #: (a folder the user picked is never second-guessed); "" when
    #: heater_log_dir served. Set by the controller, never persisted —
    #: an auto-found folder is not the user's choice.
    heater_log_fallback_dir = Str()

    #: "(found in <experiment>)" under the folder field while a
    #: fallback folder is in use, else "".
    heater_log_hint = Property(Str, observe="heater_log_fallback_dir")

    #: How many capture temperatures found no root under the figure's
    #: temperature_expression on the last derivation. Set by
    #: derive_series, never persisted.
    temperature_uninvertible = Int(0)

    #: The Axes tab's note on those gaps, "" when there are none.
    temperature_uninvertible_hint = Property(Str, observe="temperature_uninvertible")

    #: Where the heater join looked and what it found (folder, log
    #: span, capture span, any sibling stand-in) — the plot's coverage
    #: note. Set by the controller, never persisted.
    heater_log_coverage = Str()

    #: The loaded heater samples for the current capture range,
    #: [(epoch, {sensor: °C}), ...] — set by the controller, never
    #: persisted (the logs themselves are the record).
    heater_samples = List(Tuple(Float, Dict(Str, Float)))

    figure = Instance(FigureSettings, ())

    #: Image scale for the canvas bar and the area readouts.
    scale = Instance(ScaleCalibration, ())

    #: Where each ROI's background is measured (part of the cache key).
    ring = Instance(BackgroundRing, ())

    #: Frame-wide flattening applied before measuring (cache key too).
    ball = Instance(RollingBall, ())

    #: Perspective warp applied before everything else (cache key too).
    perspective = Instance(PerspectiveCorrection, ())

    #: User-typed points the Actual vs expected view plots and fits
    #: beside the ROIs' own.
    custom_points = List(Instance(CustomPoint))

    #: The Actual vs expected trend — actual = f(expected) unless flipped —
    #: None when there is nothing to fit. Set by RoiAnalysisModel; never
    #: persisted.
    trend = Instance(FitResult)

    def _get_heater_log_hint(self):
        if not self.heater_log_fallback_dir:
            return ""

        return f"(found in {Path(self.heater_log_fallback_dir).parent.name})"

    def _get_temperature_uninvertible_hint(self):
        count = self.temperature_uninvertible

        if not count:
            return ""

        if count == 1:
            return (
                "1 heater sample has no expected temperature under this "
                "expression and is drawn as a gap"
            )

        return (
            f"{count} heater samples have no expected temperature under this "
            "expression and are drawn as gaps"
        )

    def _get_positive_rois(self):
        return [roi for roi in self.rois if not roi.is_negative]

    def _get_negative_rois(self):
        return [roi for roi in self.rois if roi.is_negative]

    def roi_by_id(self, roi_id):
        for roi in self.rois:
            if roi.roi_id == roi_id:
                return roi
        return None

    def next_roi_name(self, prefix="ROI", pending=()):
        """'<prefix> N' with N one past the highest numbered existing
        name of that prefix, so a deleted ROI's number isn't reissued to
        collide with a surviving one (duplicate names would double up
        CSV columns and plot legend labels). Negative masks pass
        "Mask"; ``pending`` ROIs, built but not yet added, count too."""
        pattern = re.compile(ROI_NAME_PATTERN.format(prefix=re.escape(prefix)))
        highest = 0

        for roi in [*self.rois, *pending]:
            match = pattern.match(roi.name)

            if match:
                highest = max(highest, int(match.group(1)))

        return f"{prefix} {highest + 1}"

    def stat_info(self, path, stat_cache=None):
        """(mtime, capture_time) for ``path``. Pass a dict as
        ``stat_cache`` (path str -> (mtime, capture_time)) to memoize
        the filesystem stat and timestamp parse across many calls in
        the same pass (a rebuild calls this once per image, cache_key()
        once per image per ROI)."""
        key = str(path)
        if stat_cache is not None and key in stat_cache:
            return stat_cache[key]
        try:
            mtime = Path(path).stat().st_mtime
        except OSError:
            mtime = 0.0
        info = (mtime, capture_timestamp(path))
        if stat_cache is not None:
            stat_cache[key] = info
        return info

    def cache_key(self, path, roi, stat_cache=None):
        """Cache key for one (image, ROI) pair: the file identity/mtime
        plus the geometry in force at the image's capture time, and the
        image's correction_for() — so moving, hiding or showing any
        negative mask on an image invalidates every ROI measured on it.
        Pass ``stat_cache`` through from stat_info() to avoid re-stating
        the same path for every ROI."""
        stat_cache = {} if stat_cache is None else stat_cache
        mtime, capture_time = self.stat_info(path, stat_cache)

        return (
            str(path),
            mtime,
            roi.roi_id,
            roi.kind,
            tuple(roi.effective_geometry(capture_time)),
            self.correction_for(path, stat_cache),
        )

    def correction_key(self):
        """Everything about how the image is treated before a stat is
        read off it — the ring, the rolling ball that runs before it, and
        the perspective warp that runs first. One tuple, so the cache key
        and the work item cannot drift apart."""
        return (
            self.ring.gap_px,
            self.ring.thickness_px,
            self.ball.effective_radius(),
            self.perspective.effective_matrix(),
        )

    def negatives_for(self, path, stat_cache=None):
        """Sorted ((kind, geometry tuple), ...) of every shown negative
        mask in force for ``path``, drift overrides applied. A mask hidden
        with its eye is left out, so toggling the eye compares the numbers
        with and without it; so is a mask drawn on a later image than
        ``path`` (Roi.applies_at). The result is part of every
        cache_key() on ``path``, so both variants stay cached and
        toggling back is instant."""
        capture_time = self.stat_info(path, stat_cache)[1]

        return tuple(
            sorted(
                (roi.kind, tuple(roi.effective_geometry(capture_time)))
                for roi in self.negative_rois
                if roi.style.visible and roi.applies_at(capture_time)
            )
        )

    def correction_for(self, path, stat_cache=None):
        """correction_key() plus the negative masks in force for
        ``path`` — the work item's correction tuple, whose last element
        compute_image_stats takes as ``negatives``."""
        return self.correction_key() + (self.negatives_for(path, stat_cache),)

    def effective_for(self, path):
        """[(roi_id, name, kind, geometry, is_negative), ...] in force
        for ``path`` — what the canvas draws for that image. A mask drawn
        on a later image than ``path`` has no row (Roi.applies_at)."""
        capture_time = capture_timestamp(path)

        return [
            (
                roi.roi_id,
                roi.name,
                roi.kind,
                roi.effective_geometry(capture_time),
                roi.is_negative,
            )
            for roi in self.rois
            if roi.applies_at(capture_time)
        ]


class RoiAnalysisModel(HasTraits):
    """Shared tool-state between the viewer pane (ROI editing,
    toolbuttons) and the plot pane; the per-experiment data lives in
    ``session``."""

    #: Canvas interaction: pan (normal navigation), one-shot draw modes,
    #: edit (move/resize/select existing ROIs), or ai_pick (click the
    #: canvas to prompt SAM at that point).
    interaction_mode = Enum(
        "pan",
        "draw_ellipse",
        "draw_box",
        "draw_capsule",
        "draw_polygon",
        "draw_scale",
        "edit",
        "ai_pick",
    )

    #: roi_id of the canvas-selected ROI (edit mode), '' when none.
    selected_roi_id = Str()

    #: Batch progress readout ("12/40, 1 failed"; '' when idle).
    progress_text = Str()
    batch_total = Int(0)
    batch_done = Int(0)
    batch_failed = Int(0)
    batch_running = Bool(False)

    #: Whether the ROI plot pane is showing — mirrored from its dock
    #: visibility, so work only the plot would show (the heater join)
    #: can wait until someone can see it.
    plot_visible = Bool(False)

    #: Whether a protocol is running (PROTOCOL_RUNNING, set on the GUI
    #: thread by the image viewer's message handler): heavy analysis
    #: work asks first and the batch runs narrower.
    protocol_running = Bool(False)

    #: A draw or edit is under way during a run: the viewer holds the
    #: shown frame — no auto-follow to new captures, no refit — until
    #: it ends.
    holds_view = Property(Bool, observe="protocol_running, interaction_mode")

    def _get_holds_view(self):
        return self.protocol_running and self.interaction_mode in VIEW_HOLDING_MODES

    # Toolbar buttons (view events; RoiAnalysisController reacts).
    draw_ellipse_button = Button()
    draw_box_button = Button()
    draw_capsule_button = Button()
    draw_polygon_button = Button()
    calibrate_scale_button = Button()

    #: Live mirrors of session settings the toolbar toggles: the
    #: toolbar is built once against this model while sessions swap
    #: underneath it.
    show_background_ring = Bool(True)
    rolling_ball_enabled = Bool(False)
    perspective_enabled = Bool(False)

    #: Whether the session has a perspective transform to apply — gates
    #: the apply toggle (a top-level mirror: enabled_when does not see
    #: nested changes).
    perspective_defined = Bool(False)

    #: Opens the perspective-definition window.
    define_perspective_button = Button()
    edit_mode = Bool(False)
    delete_roi_button = Button()
    clear_rois_button = Button()
    calculate_button = Button()
    export_csv_button = Button()
    reset_cache_button = Button()
    #: Render the current plot to an image file at the session's export
    #: settings (handled by the plot dock pane, which owns the canvas).
    save_plot_button = Button()
    #: Open the non-modal table of fitted equations per ROI.
    fit_equations_button = Button()
    #: Pick the heater-log folder (handled by the plot dock pane,
    #: which owns a window to parent the directory dialog on).
    heater_dir_button = Button()
    #: Set every ROI's expected fastest change back to unset (its actual).
    reset_expected_button = Button()
    #: Write the Expected table to a CSV in the experiment's analysis folder.
    export_expected_button = Button()

    #: Put the trend's full-precision expression on the clipboard, for
    #: the heater's compensation and the temperature-axis calibration.
    copy_trend_expression_button = Button()

    #: Why Copy cannot run, the first failing condition; '' when it can.
    copy_trend_blocker = Property(
        Str,
        observe=(
            "session.trend, session.figure.x_axis, "
            "session.figure.flip_actual_expected, "
            "session.figure.temperature_expression"
        ),
    )

    #: Copy's tooltip: what it does, or why it is off.
    copy_trend_tooltip = Property(Str, observe="copy_trend_blocker")

    def _get_copy_trend_blocker(self):
        if self.session.trend is None:
            return COPY_TREND_NO_TREND

        figure = self.session.figure

        if figure.x_axis != "temperature":
            return COPY_TREND_NOT_TEMPERATURE

        # A flipped trend reads expected = f(actual), and one fitted on
        # a calibrated axis is relative to that calibration: neither is
        # the actual = f(expected) the compensation needs.
        if figure.flip_actual_expected:
            return COPY_TREND_FLIPPED

        if is_calibrated(figure):
            return COPY_TREND_CALIBRATED

        return ""

    def _get_copy_trend_tooltip(self):
        return self.copy_trend_blocker or COPY_TREND_TOOLTIP

    #: Append a blank custom point to the Expected tab's table of them.
    add_custom_point_button = Button()
    #: Drop the custom points of the cells selected in their table.
    remove_custom_point_button = Button()
    #: The custom-points table's selected cells, (point, column name)
    #: each, so the trash button knows which rows to drop.
    selected_custom_cells = List(Tuple)
    #: What the sensor dropdown offers: "mean" plus every sensor the
    #: loaded heater logs actually carry.
    heater_sensor_choices = List(Str, [HEATER_SENSOR_MEAN])

    #: View -> controller channels fired by the canvas ROI layer.
    canvas_roi_created = Event()  # (kind, geometry)
    canvas_roi_edited = Event()  # (roi_id, geometry)
    #: Escape out of an armed draw tool (which now stays armed until
    #: told otherwise, so that a series of shapes is one trip to the
    #: toolbar rather than one trip each).
    canvas_draw_cancelled = Event()

    #: Sticky toolbar toggle: while on, every draw tool creates negative
    #: masks instead of ROIs. Independent of interaction_mode.
    negative_mode = Bool(False)

    #: Display-only toolbar toggle for the canvas overlay (ROI outlines,
    #: their labels, negative masks and background rings). It never
    #: changes what is measured, plotted or exported, and is not persisted.
    show_rois = Bool(True)

    #: The user's saved fit equations [(name, expression), ...],
    #: mirrored from the app preferences that persist them so the plot
    #: and the equations table need not reach for preferences.
    fit_presets = List()

    #: Method keys the fit dropdown offers, kept in step with the saved
    #: presets and with whatever the session currently fits.
    fit_method_choices = List(Str)

    @observe("fit_presets.items, fit_presets, session, session:figure:fit_method")
    def _update_fit_method_choices(self, event):
        self.fit_method_choices = choices_for(
            self.fit_presets, self.session.figure.fit_method
        )

    def _fit_method_choices_default(self):
        return choices_for(self.fit_presets, self.session.figure.fit_method)

    #: What the View dropdown offers, mode -> label, worded for the
    #: session's x axis.
    view_mode_choices = Dict(Str, Str)

    @observe("session, session:figure:x_axis")
    def _update_view_mode_choices(self, event):
        self.view_mode_choices = VIEW_MODE_LABELS_BY_X_AXIS[self.session.figure.x_axis]

    def _view_mode_choices_default(self):
        return VIEW_MODE_LABELS_BY_X_AXIS[self.session.figure.x_axis]

    # ---------------------------------------------------------------- #
    # AI (SAM) ROI detection: toolbar/options state and canvas<->
    # controller event channels. Reacted to by RoiAnalysisController;
    # this model only holds the state.
    # ---------------------------------------------------------------- #
    #: Whether the optional SAM stack is importable (osam installed) —
    #: gates whether the AI tools are enabled in the UI.
    ai_available = Bool(False)

    #: AI toolbar buttons (view events; RoiAnalysisController reacts).
    ai_pick_button = Button()
    ai_detect_button = Button()
    ai_track_button = Button()
    ai_accept_button = Button()
    ai_clear_button = Button()

    #: Candidates from the last pick/detect/track pass, awaiting review
    #: (accept/discard) before becoming real ROIs.
    ai_candidates = List(Instance(Candidate))

    #: Significance filter: minimum grid-sweep vote count a candidate
    #: needs to survive (click-sourced candidates are exempt).
    ai_significance = Int(AI_SIGNIFICANCE_DEFAULT)
    #: Size filter: minimum mean ellipse diameter (px) a candidate needs.
    #: Candidate size window (mean ellipse diameter, px). Coupled: the
    #: observers below drag one bound along when the other crosses it,
    #: so min can never sit above max (mutually-referencing dynamic
    #: Range bounds would recurse — traits evaluates them on read).
    ai_min_size = Range(0, AI_SIZE_FILTER_CEILING_PX, AI_MIN_SIZE_DEFAULT_PX)
    ai_max_size = Range(0, AI_SIZE_FILTER_CEILING_PX, AI_MAX_SIZE_DEFAULT_PX)

    @observe("ai_min_size")
    def _keep_max_size_at_or_above_min(self, event):
        if self.ai_max_size < event.new:
            self.ai_max_size = event.new

    @observe("ai_max_size")
    def _keep_min_size_at_or_below_max(self, event):
        if self.ai_min_size > event.new:
            self.ai_min_size = event.new

    #: Geometry accepted candidates are converted to.
    ai_output_kind = Enum("polygon", "ellipse")
    #: How many images between drift re-checks while tracking.
    ai_drift_interval = Range(1, 50, AI_DRIFT_CHECK_INTERVAL_DEFAULT)
    #: Whether a track pass is currently running (drives a progress UI).
    ai_track_running = Bool(False)
    #: Drift-check progress in checked-frame units; the status-row
    #: progress readout fills from these while ai_track_running (the
    #: batch counts it otherwise fills from are stale during a track).
    ai_track_done = Int(0)
    ai_track_total = Int(0)
    #: Count of ROIs accepted from AI candidates this session (readout).
    ai_accept_count = Int(0)

    #: Canvas click while in "ai_pick" interaction mode. # (x, y)
    canvas_ai_pick = Event()
    #: Canvas click on a candidate overlay. # candidate index
    canvas_candidate_clicked = Event()
    #: Accepted candidates converted to ROIs. # (pairs, anchor), where
    #: pairs is [(kind, geometry), ...] and anchor is the capture time
    #: they were accepted against.
    ai_rois_accepted = Event()
    #: One ROI's geometry updated by a drift re-check while tracking.
    #: # (roi_id, capture_time, geometry)
    ai_roi_tracked = Event()

    #: The ROI shape held for pasting: kind and the geometry it had on
    #: the image it was copied from ('' = nothing copied yet). Not the
    #: system clipboard, and deliberately not persisted.
    copy_roi_button = Button()
    paste_roi_button = Button()
    clipboard_kind = Str()
    clipboard_geometry = List(Float)

    #: Whether the copied shape was a negative mask, so a paste
    #: reproduces it as one whatever negative_mode says.
    clipboard_negative = Bool(False)

    #: The per-experiment analysis state (swapped on experiment change).
    session = Instance(AnalysisSession, ())

    #: History of changes to the session's drawn shapes (create, edit,
    #: delete, clear) — see roi_commands. Style, visibility and settings
    #: changes stay out of it. Emptied whenever the session is swapped.
    undo_stack = Instance(CommandStack)

    #: Step back / forward through ``undo_stack`` (toolbar, Ctrl+Z /
    #: Ctrl+Y on the canvas); RoiAnalysisController reacts.
    undo_roi_button = Button()
    redo_roi_button = Button()

    #: Whether there is a step to undo / redo — top-level mirrors of the
    #: stack for the buttons' enabled_when.
    can_undo = Bool(False)
    can_redo = Bool(False)

    def _undo_stack_default(self):
        # A CommandStack cannot push without an undo manager to number
        # its commands and announce stack_updated.
        manager = UndoManager()
        stack = CommandStack(undo_manager=manager)
        manager.active_stack = stack

        return stack

    @observe("session")
    def _forget_history(self, event):
        self.undo_stack.clear()

    @observe("undo_stack:undo_manager:stack_updated")
    def _mirror_undo_state(self, event):
        self.can_undo = self.undo_stack.undo_name != ""
        self.can_redo = self.undo_stack.redo_name != ""

    #: Mirrors of the viewer's filtered image list and displayed image
    #: (str paths), maintained by RoiAnalysisController so the plot
    #: pane and stats table never need the viewer model.
    filtered_paths = List(Str)
    current_image_path = Str()

    #: Each ROI's fitted landmark x values, {roi_id: {metric: x}}, pushed
    #: by the plot canvas — the only place the fits are computed — after
    #: every redraw, whatever view it shows. A landmark the fit lacks is
    #: left out; empty while fitting is off.
    expected_actuals = Dict(Str, Dict(Str, Float))

    #: The Expected table's rows, one per positive ROI per compared
    #: landmark, grouped by ROI.
    expected_rows = Property(
        List(Instance(ExpectedRow)),
        observe="session, session:rois.items, session:rois:items:is_negative, "
        "session:figure:compare_second_derivative_max, "
        "session:figure:compare_second_derivative_min",
    )

    @cached_property
    def _get_expected_rows(self):
        return [
            ExpectedRow(
                roi=roi,
                metric=metric,
                actual=self.expected_actuals.get(roi.roi_id, {}).get(metric, math.nan),
            )
            for roi in self.session.positive_rois
            for metric in self.session.figure.compared_metrics
        ]

    @observe("expected_actuals")
    def _update_expected_actuals(self, event):
        for row in self.expected_rows:
            actuals = self.expected_actuals.get(row.roi.roi_id, {})
            row.actual = actuals.get(row.metric, math.nan)

    @observe(
        "expected_actuals, session, session:figure:fit_method, "
        "session:figure:trend_method, session:figure:flip_actual_expected, "
        "session:custom_points.items, session:custom_points:items:actual, "
        "session:custom_points:items:expected, "
        "session:rois:items:expected_fastest_change, "
        "session:rois:items:expected_second_derivative_max, "
        "session:rois:items:expected_second_derivative_min"
    )
    def _update_trend(self, event):
        figure = self.session.figure

        # The view draws no points with fitting off, so no trend either.
        if figure.fit_method == "none":
            self.session.trend = None

            return

        self.session.trend = trend_fit(
            *trend_points(self.session, self.expected_actuals), figure.trend_method
        )

    #: Whether the DISPLAYED image is excluded from analysis — the
    #: sidebar checkbox edits this; RoiAnalysisController mirrors it
    #: against session.excluded_images in both directions.
    current_image_excluded = Bool(False)

    #: A click on a curves-view point: toggle that image's exclusion
    #: and show it. RoiAnalysisController reacts. # image path (str)
    toggle_exclusion_request = Event()

    #: Bulk exclusion: mark (exclude) or unmark (include) every image
    #: before / after the displayed one (exclusive) with the checkbox
    #: above's exclusion.
    exclude_before_button = Button("Before")
    exclude_after_button = Button("After")
    include_before_button = Button("Before")
    include_after_button = Button("After")

    #: Unmark every image of the experiment at once: the include
    #: buttons above with no shown image to count from.
    include_all_button = Button("All")


#: The single analysis state shared by the viewer pane and the plot pane
#: (both owned by this plugin) — the media_capture_event_model pattern.
roi_analysis_model = RoiAnalysisModel()

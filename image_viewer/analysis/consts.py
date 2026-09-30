# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Constants for the ROI intensity-analysis subpackage."""

#: Background annulus: how far outside the ROI edge it starts, and how
#: thick it is, in pixels. The gap exists because fluorescence bleeds a
#: pixel or two past the boundary and that halo is not background.
RING_GAP_PX = 2
RING_THICKNESS_PX = 4

#: Default rolling-ball radius (px): the scale of unevenness removed
#: from the whole frame before any ROI is measured. Comfortably larger
#: than a droplet, or the ball rolls over the signal too.
ROLLING_BALL_RADIUS_PX = 50

# --------------------------------------------------------------------
# (min, max) bounds of every user-editable number. Each is read by the
# model trait AND by the spinner that edits it — and, for the ball, by
# the canvas drag that sets it — so one definition keeps the copies
# from drifting apart.
# --------------------------------------------------------------------
#: Ring gap / thickness (px). Gap may be 0 (ring hugs the shape); the
#: ring itself needs at least one pixel of width to exist.
RING_GAP_BOUNDS_PX = (0, 50)
RING_THICKNESS_BOUNDS_PX = (1, 50)
#: Rolling-ball radius (px): below 5 the ball is smaller than the
#: features it must clear; 500 exceeds any unevenness a frame carries.
ROLLING_BALL_RADIUS_BOUNDS_PX = (5, 500)
#: Per-ROI plot opacity, as a percentage.
ROI_ALPHA_BOUNDS_PCT = (0, 100)
#: Hampel outlier test: how far from the local median counts (in
#: scaled MADs, so 3 reads like "3 sigma"), and the window it is
#: judged in (odd sizes centre; 3 is the fewest with any neighbours).
OUTLIER_THRESHOLD_BOUNDS_MAD = (1.0, 20.0)
OUTLIER_THRESHOLD_MAD = 3.0
OUTLIER_WINDOW_BOUNDS_PTS = (3, 51)
OUTLIER_WINDOW_PTS = 5
#: Savitzky-Golay smoothing: points per polynomial fit and its order
#: (the filter itself needs order < window; 6 is past any curvature a
#: capture series shows).
SAVGOL_WINDOW_BOUNDS_PTS = (3, 101)
SAVGOL_WINDOW_PTS = 7
SAVGOL_ORDER_BOUNDS = (1, 6)
SAVGOL_ORDER = 2
#: Butterworth smoothing: filter order (8 is already a sharp cliff)
#: and cutoff as a fraction of the Nyquist frequency (1.0 would pass
#: everything; 0.99 keeps the filter well-posed).
BUTTER_ORDER_BOUNDS = (1, 8)
BUTTER_ORDER = 2
BUTTER_CUTOFF_BOUNDS = (0.01, 0.99)
BUTTER_CUTOFF = 0.2

#: Prefix on the outline-ring stat columns (outline_mean, outline_std, ...).
OUTLINE_STATS_PREFIX = "outline_"

#: Per-experiment folder holding analysis outputs (CSV exports and the
#: persisted ROI definitions).
ANALYSIS_DIR_NAME = "analysis"

#: Persisted ROI definitions (bases + overrides) inside ANALYSIS_DIR_NAME.
ROI_CONFIG_FILENAME = "roi_config.json"

#: Cadence (ms) of the GUI-thread timer draining finished batch results
#: into the model. Fine-grained on purpose: the drain itself is cheap
#: (the expensive redraw is coalesced separately), and a coarser tick
#: is what made the count jump in chunks rather than climb.
ANALYSIS_RESULT_DRAIN_INTERVAL_MS = 50

#: Coalescing delay (ms) between an analysis-state notification and the
#: plot redraw — a drain burst paints once.
ROI_PLOT_COALESCE_MS = 100

#: The same delay while a batch is running. A redraw refits every ROI
#: over the whole series, which measurably crowds the GUI thread: at
#: the idle cadence the redraws queue back to back and the progress
#: readout the user is watching never gets painted.
ROI_PLOT_BATCH_COALESCE_MS = 1000

#: Wheel-zoom step on the plot canvas: one notch multiplies the span
#: by this going in, and by its reciprocal going out. Matches the
#: image canvas's 1.25/0.8 so the two feel the same.
PLOT_ZOOM_STEP = 0.8

#: Below this the plot canvas stops shrinking and the plot pane's
#: scroll area takes over with scrollbars instead.
ROI_PLOT_CANVAS_MIN_WIDTH = 300
ROI_PLOT_CANVAS_MIN_HEIGHT = 200

#: Height the plot pane's controls open at. They share a splitter with
#: the chart and the table, so this is a starting point the user drags
#: from, not a cap — the controls scroll inside whatever height they
#: end up with.
ROI_PLOT_CONTROLS_MAX_HEIGHT = 180

#: Shortest a splitter section may be dragged. Small enough to tuck a
#: section away, large enough to grab its handle again.
ROI_PLOT_SECTION_MIN_PX = 40

#: Smallest ROI dimension (radius / box side, px) a canvas drag may create.
MIN_ROI_SIZE_PX = 3.0

#: Rotation-grip snap (degrees) while Shift is held.
ROTATE_SNAP_DEGREES = 15.0

#: How far (image px, down and right) a pasted ROI lands from the one
#: it was copied from, so it cannot hide underneath it.
PASTE_OFFSET_PX = 12.0

#: Fewest vertices a contour ROI can close on.
MIN_POLYGON_POINTS = 3

#: How near (image px) a click must land on a contour's first node to
#: close it while drawing.
POLYGON_CLOSE_DISTANCE_PX = 8.0

#: Default per-ROI plot colors, cycled at creation (matplotlib tab10).
DEFAULT_ROI_COLORS = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
)

#: Plot pane view modes: the intensity chart, the fits' second-
#: derivative curves, or the per-ROI time-of-fastest-change bars.
VIEW_MODES = ("intensity", "second_derivative", "fastest_change")
VIEW_MODE_LABELS = {
    "intensity": "Intensity",
    "second_derivative": "2nd derivative",
    "fastest_change": "Fastest change",
}

#: What the curves are plotted against: elapsed capture time, or the
#: heater log's temperature at each capture, joined on wall-clock time.
X_AXIS_MODES = ("time", "temperature")
X_AXIS_LABELS = {"time": "Time (s)", "temperature": "Temperature (°C)"}

#: Experiment subfolder the heater plugin writes its JSONL logs into.
HEATER_LOGS_DIR_NAME = "heater_logs"

#: Seconds of heater samples kept beyond each end of the capture
#: range, so interpolation has bracketing points at the edges.
HEATER_SAMPLE_MARGIN_S = 60.0

#: The sensor choice averaging every thermistor on a log line.
HEATER_SENSOR_MEAN = "mean"

#: Averaging window (ms) for the heater join: a capture's temperature
#: is the mean of every sample within ±window/2 of it — how generous
#: the match in time is allowed to be when the two clocks don't line
#: up sample-for-sample. Milliseconds, for fine-grained control at
#: burst cadences. 0 means exact: linear interpolation at the capture
#: instant. The ceiling (5 min) comfortably spans any logger dropout.
HEATER_WINDOW_BOUNDS_MS = (0, 300_000)
HEATER_WINDOW_MS = 0

#: Persisted computed-stats store inside ANALYSIS_DIR_NAME.
ROI_STATS_FILENAME = "roi_stats.json"

#: Fitted parameters, written beside each CSV export: equation ->
#: ROI -> {parameter: fitted value}.
FIT_EQUATIONS_FILENAME = "fit_equations.json"

#: Seconds of quiet since the last change before a debounced write of
#: the stats store.
STATS_SAVE_DEBOUNCE_S = 2.0

# --------------------------------------------------------------------------- #
# AI (SAM) ROI detection                                                       #
# --------------------------------------------------------------------------- #
#: Percentile stretch bounds fed to the SAM encoder (PROTO imaging.py:
#: the high bound must sit below saturated glare or droplet rings vanish).
AI_NORMALIZE_LOW_PERCENTILE = 1.0
AI_NORMALIZE_HIGH_PERCENTILE = 99.5
#: Width the frame is downscaled to before encoding (models resize to
#: ~1024 internally, so nothing is lost).
AI_ENCODE_WORK_WIDTH_PX = 1920
#: Target prompt count for the detect-all grid sweep.
AI_DETECT_GRID_TARGET_POINTS = 144
#: Detect-all mask sanity bounds: reject specks and background grabs.
AI_DETECT_MIN_MASK_AREA_PX = 500
AI_DETECT_MAX_MASK_AREA_FRACTION = 0.35
#: Default candidate filters and drift-check interval (options row).
AI_SIGNIFICANCE_DEFAULT = 2
AI_MIN_SIZE_DEFAULT_PX = 0
AI_MAX_SIZE_DEFAULT_PX = 500
AI_DRIFT_CHECK_INTERVAL_DEFAULT = 3

#: Candidate preview outline on the canvas: a colour distinct from the
#: ROI cyan / selected-amber / ball-violet family, the dashed pen's
#: width, and how dim a discarded candidate reads (dimmed, not
#: removed — a discard is a toggle the user might flip back).
AI_CANDIDATE_COLOR = "#ff00e5"
AI_CANDIDATE_PEN_WIDTH_PX = 1.5
AI_CANDIDATE_DISCARDED_OPACITY = 0.3
#: Hard ceiling of the candidate size filters (mean ellipse diameter,
#: px).
AI_SIZE_FILTER_CEILING_PX = 50000

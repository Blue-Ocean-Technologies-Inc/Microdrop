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
#: ring itself needs at least one pixel of width to exist. 500 leaves
#: room to clear the halo of a droplet hundreds of pixels across.
RING_GAP_BOUNDS_PX = (0, 500)
RING_THICKNESS_BOUNDS_PX = (1, 500)
#: Rolling-ball radius (px): below 5 the ball is smaller than the
#: features it must clear; 500 exceeds any unevenness a frame carries.
ROLLING_BALL_RADIUS_BOUNDS_PX = (5, 500)
#: The line styles and markers a plotted line can take (RoiStyle,
#: the temperature view's styles); the first is each one's default.
LINE_STYLE_NAMES = ("solid", "dashed", "dotted", "dashdot")
MARKER_NAMES = ("none", ".", "o", "s", "^", "x")
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

#: A mask is 8-bit: this is "inside", and 0 is "outside". Every mask
#: the analysis draws, tests and combines uses it, so it is one name
#: rather than a 255 sprinkled through the files.
MASK_ON = 255

#: The droplet-shape quantities, in Plot-dropdown, table and CSV order.
#: None scales with the calibration: all are unitless but the
#: orientation, an angle in degrees. "shape_change" is the one series
#: quantity: each image's distance from the ROI's first analysed image
#: with a droplet.
SHAPE_STATS = (
    "circularity",
    "shape_change",
    "axis_ratio",
    "eccentricity",
    "solidity",
    "extent",
    "orientation_deg",
)

#: The area-normalised means, each with the integrated stat it divides
#: by the ROI's reference area (its pixel count on the first analysed
#: image with stats) — a series quantity like "shape_change".
AREA_NORMALIZED_STATS = {
    "area_normalized": "integrated",
    "bg_area_normalized": "bg_integrated",
}

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

#: Images an ROI batch computes at once while a protocol runs, however
#: wide the shared pool: the run's captures and device I/O need the
#: rest of the CPU.
ROI_BATCH_PROTOCOL_WORKERS = 2

#: Canvas modes during which a running protocol's new captures do not
#: take over the view (no auto-follow, no refit) — a shape half drawn
#: or being edited would otherwise land on a different frame.
VIEW_HOLDING_MODES = (
    "draw_ellipse",
    "draw_box",
    "draw_capsule",
    "draw_polygon",
    "draw_scale",
    "edit",
)

#: Asked before heavy analysis work (Calculate, Export, AI Detect/Track)
#: starts while a protocol runs.
PROTOCOL_RUNNING_CONFIRM_MESSAGE = (
    "A protocol is running; this can stall the app and delay captures. Continue?"
)

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

#: The delete dialog's choices: take the selected ROI off the shown
#: image only, or remove it from every image.
DELETE_ROI_THIS_IMAGE = "This image only"
DELETE_ROI_LATER_IMAGES = "This and later images"
DELETE_ROI_EARLIER_IMAGES = "This and earlier images"
DELETE_ROI_ALL_BUT_THIS = "All except this image"
DELETE_ROI_ALL_IMAGES = "All images"

#: What deleting an ROI does (ImageViewerPreferences.roi_delete_scope),
#: by preference value: ask with the dialog above, or apply one of its
#: choices without asking — the label each has on the preferences tab.
ROI_DELETE_SCOPES = {
    "ask": "Ask each time",
    "image": DELETE_ROI_THIS_IMAGE,
    "later": DELETE_ROI_LATER_IMAGES,
    "earlier": DELETE_ROI_EARLIER_IMAGES,
    "except": DELETE_ROI_ALL_BUT_THIS,
    "all": DELETE_ROI_ALL_IMAGES,
}

#: The scopes that take an ROI off some images and keep it on the rest.
#: Roi.absent_by names the first three the same way; "except" is the
#: two ranges stopping either side of the shown image.
ROI_ABSENCE_SCOPES = ("image", "later", "earlier", "except")

#: The delete dialog's checkbox, worded as the experiment delete's is.
ROI_DELETE_DONT_ASK_TEXT = "Don't ask again (change under Preferences › Image Viewer)"

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

#: Outline colour of every negative mask — a vivid pink-red that none
#: of DEFAULT_ROI_COLORS nor AI_CANDIDATE_COLOR uses, so a cut-out never
#: reads as an ROI or a pending candidate. Masks do not take a slot in
#: the ROI colour cycle.
NEGATIVE_MASK_COLOR = "#ff2d55"

#: Name prefix of negative masks ("Mask 1", "Mask 2", ...), numbered
#: apart from the "ROI N" sequence.
NEGATIVE_MASK_NAME_PREFIX = "Mask"

#: Plot pane view modes: the plotted stat over time (the key predates
#: the area stat and is persisted, so it stays "intensity"), its value
#: per ROI on the displayed image, its distribution per ROI across the
#: series, the fits' first- or second-derivative curves, the per-ROI
#: time-of-fastest-change bars, that time against the one the user
#: expects, or the heater log's temperature over the captures' time.
VIEW_MODES = (
    "intensity",
    "per_image",
    "distribution",
    "first_derivative",
    "second_derivative",
    "fastest_change",
    "actual_vs_expected",
    "temperature",
)
VIEW_MODE_LABELS = {
    "intensity": "Over time",
    "per_image": "Per image",
    "distribution": "Distribution",
    "first_derivative": "1st derivative",
    "second_derivative": "2nd derivative",
    "fastest_change": "Fastest change",
    "actual_vs_expected": "Actual vs expected",
    "temperature": "Temperature over time",
}

#: The fitted-curve landmarks the Expected tab can compare against the
#: user's expected values: where the second derivative crosses zero
#: (the fastest change, always compared), peaks, and troughs. Their
#: table labels, and the Actual vs expected view's scatter markers.
EXPECTED_METRICS = ("zero", "max", "min")
EXPECTED_METRIC_LABELS = {"zero": "d² zero", "max": "d² max", "min": "d² min"}
EXPECTED_METRIC_MARKERS = {"zero": "o", "max": "^", "min": "v"}

#: How the Expected tab's custom (user-typed) points are drawn in the
#: Actual vs expected view — black squares, apart from every ROI's
#: coloured landmarks — and their legend label.
CUSTOM_POINT_MARKER = "s"
CUSTOM_POINT_COLOR = "black"
CUSTOM_POINT_ALPHA = 0.8
CUSTOM_POINT_LABEL = "Custom"

#: Why the Expected tab's Copy (the trend as actual = f(expected)) is
#: off, in the order they are checked, and its tooltip when it is on.
COPY_TREND_NO_TREND = (
    "No trend fitted yet: pick a fit method so the Actual vs expected view has points"
)
COPY_TREND_NOT_TEMPERATURE = (
    "Plot against temperature: a time-axis trend is no temperature compensation"
)
COPY_TREND_FLIPPED = (
    "Unflip the axes: flipped, the trend reads expected = f(actual), "
    "the wrong direction"
)
COPY_TREND_CALIBRATED = "Clear the axis calibration to copy a fresh one"
COPY_TREND_TOOLTIP = (
    "Copy the trend as actual = f(expected) at full precision, for the "
    "heater's compensation and this plot's temperature calibration (the "
    "corner equation is rounded to 3 significant figures)"
)

#: The View labels per x axis: only the curves view names its axis.
VIEW_MODE_LABELS_BY_X_AXIS = {
    "time": VIEW_MODE_LABELS,
    "temperature": {**VIEW_MODE_LABELS, "intensity": "Over temperature"},
    "step": {**VIEW_MODE_LABELS, "intensity": "Over steps"},
    "frame": {**VIEW_MODE_LABELS, "intensity": "Over frames"},
}

#: What the curves are plotted against: elapsed capture time, the
#: heater log's temperature at each capture (joined on wall-clock
#: time), the protocol step each capture was taken in, or the image's
#: position in the filtered series. The time label carries no unit:
#: the unit picker beside it says which.
X_AXIS_MODES = ("time", "temperature", "step", "frame")
X_AXIS_LABELS = {
    "time": "Time",
    "temperature": "Temperature (°C)",
    "step": "Protocol step",
    "frame": "Frame",
}

#: Units the time axis offers (the first is the default), and each
#: one's count per second of elapsed capture time.
TIME_UNITS = ("s", "min", "ms")
TIME_UNIT_PER_SECOND = {"s": 1.0, "min": 1.0 / 60.0, "ms": 1000.0}

#: How near (display px) a click on the curves view must land to a
#: drawn point to toggle its image's exclusion.
PLOT_PICK_RADIUS_PX = 8

#: How far (display px) the pointer may drift between press and
#: release and still count as a click rather than a pan — a hand
#: rarely holds a mouse dead still.
PLOT_CLICK_SLOP_PX = 3

#: Excluded images' points on the curves view: hollow markers in each
#: ROI's colour, this opaque, so they stay visible and clickable
#: without reading as part of the analysis.
EXCLUDED_POINT_ALPHA = 0.35
EXCLUDED_POINT_MARKER = "o"

#: The Temperature over time view: how far past the filtered captures'
#: span the log is drawn each side, as a fraction of that span with a
#: floor (s) for a run of one capture. How it is drawn is the
#: experiment's TemperaturePlotStyle.
TEMPERATURE_VIEW_MARGIN_FRACTION = 0.05
TEMPERATURE_VIEW_MARGIN_MIN_S = 10.0

#: Experiment subfolder the heater plugin writes its JSONL logs into.
HEATER_LOGS_DIR_NAME = "heater_logs"

#: Seconds of heater samples kept beyond each end of the capture
#: range, so interpolation has bracketing points at the edges.
HEATER_SAMPLE_MARGIN_S = 60.0

#: How many of the most recent sibling experiments are searched for a
#: heater log when the experiment's own folder covers none of its
#: captures (the heater plugin has filed a run's log under the
#: previous experiment).
HEATER_SIBLING_SEARCH_LIMIT = 10

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

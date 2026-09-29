# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Series derivation for the ROI plot: a pure function of the session
and the viewer's filtered paths, so the plot pane owns its own picture
(observer pattern — nothing pushes series at it). Qt-free."""

# Standard library imports.
import math

# Local imports.
from ..scale_bar import pixel_area
from .consts import (
    BUTTER_CUTOFF,
    BUTTER_CUTOFF_BOUNDS,
    BUTTER_ORDER_BOUNDS,
    OUTLIER_THRESHOLD_MAD,
    OUTLIER_WINDOW_PTS,
    SAVGOL_ORDER,
    SAVGOL_WINDOW_PTS,
)
from .heater_log import temperature_at

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _signal(stats, background):
    """The mean, or the mean less the outline ring when ``background``.
    NaN when either piece is missing."""
    mean = stats.get("mean")
    if mean is None:
        return math.nan
    if not background:
        return mean
    outline = stats.get("outline_mean")
    return math.nan if outline is None else mean - outline


def _count(stats):
    """The interior pixel count, or NaN — which then propagates through
    whatever it is multiplied into."""
    count = stats.get("count")
    return math.nan if count is None else count


def stat_value(stats, stat, pixel_area=1.0):
    """The plotted value for one (image, ROI) stats dict — NaN when the
    stats are missing entirely or lack the pieces a stat needs.
    ``bg_corrected`` is interior mean minus outline-ring mean.
    ``pixel_area`` is one pixel's area in the display unit (1.0 = px²),
    which the size-aware stats scale by."""
    if not stats:
        return math.nan
    if stat == "bg_corrected":
        return _signal(stats, True)
    if stat == "integrated":
        return _signal(stats, False) * _count(stats)
    if stat == "bg_integrated":
        return _signal(stats, True) * _count(stats)
    if stat == "per_area":
        return _signal(stats, False) / pixel_area
    if stat == "bg_per_area":
        return _signal(stats, True) / pixel_area
    if stat == "area":
        return _count(stats) * pixel_area
    value = stats.get(stat)
    return math.nan if value is None else value


def derive_series(session, filtered_paths):
    """{roi_id: (name, [x], [value])} for ``session.plot_stat`` over
    the filtered images. The x is elapsed seconds from the first
    filtered capture — or, when the figure's x_axis says so, the
    heater log's temperature at each capture (NaN where the log does
    not cover it), so the fits downstream read against °C too.
    NaN where an (image, ROI) pair has no computed stats (line gaps).
    User-excluded images are left out entirely (no gap: they are not
    part of the analysis)."""
    paths = [path for path in filtered_paths if not session.is_excluded(path)]
    if not paths or not session.rois:
        return {}
    stat_cache = {}
    # Named to leave the imported pixel_area() function reachable.
    area_per_pixel = pixel_area(session.scale.metres_per_pixel, session.scale.unit)
    times = [session.stat_info(path, stat_cache)[1] for path in paths]
    start_time = times[0]
    figure = session.figure
    x_values = (
        temperature_at(
            session.heater_samples,
            figure.heater_sensor,
            times,
            figure.heater_window_ms / 1000.0,
        )
        if figure.x_axis == "temperature"
        else [capture_time - start_time for capture_time in times]
    )
    series = {}
    for roi in session.rois:
        elapsed, values = [], []
        for index, path in enumerate(paths):
            stats = session.stats.get(session.cache_key(path, roi, stat_cache))
            elapsed.append(x_values[index])
            values.append(stat_value(stats, session.plot_stat, area_per_pixel))
        series[roi.roi_id] = (roi.name, elapsed, values)
    return series


def subtracted_series(series):
    """``series`` with each curve less its own first finite value, so
    every ROI starts at zero and shows change from baseline. NaN stays
    NaN; a curve with no finite value passes through untouched."""
    shifted = {}
    for roi_id, (name, elapsed, values) in series.items():
        first = next((value for value in values if value == value), None)
        shifted[roi_id] = (
            name,
            elapsed,
            values
            if first is None
            else [value if value != value else value - first for value in values],
        )
    return shifted


#: Scale factor making a median absolute deviation comparable to a
#: standard deviation for normally distributed data, so a threshold of
#: 3 means about what "3 sigma" means — without a single wild value
#: inflating the scale it is tested against, as an SD would.
MAD_TO_SIGMA = 1.4826

#: The same for a MEAN absolute deviation, used only where the median
#: one collapses to zero (see _robust_scale).
MEAN_ABS_TO_SIGMA = 1.2533

#: Fewest finite points a median or a Hampel window can say
#: anything about — below three there are no neighbours to
#: disagree with.
_MIN_MEDIAN_POINTS = 3

#: filtfilt pads the signal with a few filter-lengths of
#: reflection at each end; scipy needs the series longer than
#: this multiple of the order, or it raises.
_FILTFILT_MIN_LENGTH_MULTIPLE = 3


def _robust_scale(values, centre):
    """A spread for ``values`` about ``centre``, in units comparable
    to a standard deviation.

    The median absolute deviation, except where that is zero — which
    happens whenever half the values are identical, as in a steady
    signal, a quantised one, or a two-level flicker. The median then
    says there is no spread while the data plainly has some, so the
    MEAN absolute deviation stands in: it still resists a spike (one
    value in twenty pulls it by a twentieth) without vanishing."""
    deviations = [abs(value - centre) for value in values]
    middle = MAD_TO_SIGMA * _median(deviations)
    if middle > 0.0:
        return middle
    return MEAN_ABS_TO_SIGMA * (sum(deviations) / len(deviations))


def _window_slice(values, index, window):
    half = window // 2
    return values[max(index - half, 0) : index + half + 1]


def outlier_mask(values, threshold=OUTLIER_THRESHOLD_MAD, window=OUTLIER_WINDOW_PTS):
    """Which points are outliers, by the Hampel test: each point
    against the median and median-absolute-deviation of the window
    around it.

    Robust by construction — the spike being tested cannot drag the
    median it is compared against, where a mean-and-SD test lets one
    wild value raise the very threshold that would have caught it.

    Where a window's own spread collapses (see _robust_scale) the
    whole series' stands in, so the case the test exists for — a
    steady signal with one bad frame — is not missed for want of a
    scale.

    Its limit is the window: outliers close enough together to fill
    much of one stop being outliers relative to each other, and the
    test goes quiet. Widening the window pushes that out only until
    the window spans real changes in the signal. Isolated spikes, the
    usual case, are what this catches."""
    finite = [value for value in values if value == value]
    if len(finite) < _MIN_MEDIAN_POINTS:
        return [False] * len(values)
    window = max(int(window), _MIN_MEDIAN_POINTS)
    overall_scale = _robust_scale(finite, _median(finite))
    flags = []
    for index, value in enumerate(values):
        if value != value:
            flags.append(False)  # a gap is not an outlier
            continue
        neighbours = [
            other for other in _window_slice(values, index, window) if other == other
        ]
        if len(neighbours) < _MIN_MEDIAN_POINTS:
            flags.append(False)
            continue
        middle = _median(neighbours)
        deviation = abs(value - middle)
        scale = _robust_scale(neighbours, middle) or overall_scale
        flags.append(deviation > threshold * scale if scale > 0.0 else deviation > 0.0)
    return flags


def _median(values):
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def without_outliers(
    series, threshold=OUTLIER_THRESHOLD_MAD, window=OUTLIER_WINDOW_PTS
):
    """``series`` with outlying points replaced by NaN — the same hole
    an uncomputed image leaves, so everything downstream already knows
    how to skip it. Returns (series, {roi_id: [flags]}) so the plot can
    mark what it dropped rather than quietly losing it."""
    cleaned, flagged = {}, {}
    for roi_id, (name, elapsed, values) in series.items():
        flags = outlier_mask(values, threshold, window)
        flagged[roi_id] = flags
        cleaned[roi_id] = (
            name,
            elapsed,
            [math.nan if flag else value for value, flag in zip(values, flags)],
        )
    return cleaned, flagged


def background_ref_baseline(session, series):
    """The per-image background from the ROIs marked as background
    references: the mean of their values at each point, over whichever
    of them have one. None when no ROI is marked — the caller reports
    that rather than correcting by nothing.

    NaN where no reference has a value for an image, so the correction
    gaps there instead of quietly leaving that image uncorrected among
    corrected ones."""
    columns = [
        values
        for roi_id, (_name, _elapsed, values) in series.items()
        if (
            session.roi_by_id(roi_id) is not None
            and session.roi_by_id(roi_id).is_background_ref
        )
    ]
    if not columns:
        return None
    baseline = []
    for index in range(max((len(values) for values in columns), default=0)):
        present = [
            values[index]
            for values in columns
            if index < len(values) and values[index] == values[index]
        ]
        baseline.append(sum(present) / len(present) if present else math.nan)
    return baseline


def background_ref_corrected_series(session, series):
    """``series`` less the background references' mean at each image —
    regions holding no signal, measured in the same frame as the
    samples.

    Pass the FULL series, before hidden ROIs are dropped: the
    references are exactly the curves a user hides once they have
    served their purpose, and reading the baseline from the filtered
    set would let that click switch the correction off."""
    baseline = background_ref_baseline(session, series)
    if baseline is None:
        return series
    corrected = {}
    for roi_id, (name, elapsed, values) in series.items():
        corrected[roi_id] = (
            name,
            elapsed,
            [
                value - baseline[index] if index < len(baseline) else math.nan
                for index, value in enumerate(values)
            ],
        )
    return corrected


def normalized_series(series):
    """``series`` with each ROI stretched to 0-100% of its own finite
    range, so curves of wildly different brightness can be compared for
    shape and timing. NaN stays NaN, so a gap stays a gap; a curve with
    no range (min == max) sits flat at 0%, there being nothing to
    stretch and no span to divide by."""
    scaled = {}
    for roi_id, (name, elapsed, values) in series.items():
        finite = [value for value in values if value == value]
        low = min(finite) if finite else 0.0
        span = (max(finite) - low) if finite else 0.0
        scaled[roi_id] = (
            name,
            elapsed,
            [
                value
                if value != value
                else (0.0 if span == 0 else (value - low) / span * 100.0)
                for value in values
            ],
        )
    return scaled


def visible_series(session, series):
    """``series`` less the ROIs whose eye is off (and any entry whose
    ROI is gone). Applied once per redraw, so every view the figure
    offers hides the same ROIs; the stats table and the CSV, which are
    data rather than figure, keep them all."""
    shown = {}
    for roi_id, entry in series.items():
        roi = session.roi_by_id(roi_id)
        if roi is not None and roi.style.visible:
            shown[roi_id] = entry
    return shown


#: Smoothers the plot offers, in dropdown order.
SMOOTH_METHODS = ("none", "savgol", "butterworth")
SMOOTH_LABELS = {
    "none": "No smoothing",
    "savgol": "Savitzky-Golay",
    "butterworth": "Butterworth",
}


def _bridge_gaps(values):
    """``values`` with each internal NaN run replaced by the straight
    line between its two finite neighbours. Leading and trailing NaNs
    stay NaN — with nothing on the far side there is no line to draw."""
    known = [(index, value) for index, value in enumerate(values) if value == value]
    bridged = list(values)
    for (left_index, left), (right_index, right) in zip(known, known[1:]):
        span = right_index - left_index
        for index in range(left_index + 1, right_index):
            bridged[index] = left + (right - left) * (index - left_index) / span
    return bridged


def interpolated_series(series):
    """``series`` with each curve's internal gaps bridged — display
    dressing for lines matplotlib would otherwise break at every NaN.
    Only the DRAWN lines go through this: an interpolated value is
    invented data, and the fits, the CSV and the stats table keep the
    gaps."""
    return {
        roi_id: (name, elapsed, _bridge_gaps(values))
        for roi_id, (name, elapsed, values) in series.items()
    }


def _fill_gaps(values):
    """(filled, gaps): the series with internal NaNs interpolated and
    the ends held flat, plus where they were.

    Both smoothers need a continuous, evenly spaced signal — one NaN
    would otherwise spread across the whole window — so the holes are
    filled for the filter and punched back out afterwards. A gap is
    missing data, and smoothing must not invent a value there."""
    gaps = [value != value for value in values]
    known = [(index, value) for index, value in enumerate(values) if value == value]
    if not known:
        return None, gaps
    filled = _bridge_gaps(values)
    (first_index, first), (last_index, last) = known[0], known[-1]
    for index in range(first_index):
        filled[index] = first
    for index in range(last_index + 1, len(filled)):
        filled[index] = last
    return filled, gaps


def _restore_gaps(values, gaps):
    return [math.nan if gap else value for value, gap in zip(values, gaps)]


def smoothed_values(
    values, method, window=SAVGOL_WINDOW_PTS, order=SAVGOL_ORDER, cutoff=BUTTER_CUTOFF
):
    """One series smoothed, or returned untouched when it is too short
    for the filter asked for — a curve that cannot be smoothed is shown
    as it is rather than not at all.

    Both filters treat the points as evenly spaced. Captures are
    usually on a fixed interval; where they are not, the smoothing is
    over POINTS rather than seconds, which is the honest reading of
    what a window means here."""
    if method not in ("savgol", "butterworth"):
        return list(values)
    filled, gaps = _fill_gaps(values)
    if filled is None:
        return list(values)
    from scipy.signal import butter, filtfilt, savgol_filter

    count = len(filled)
    try:
        if method == "savgol":
            # An even window has no centre point, and the polynomial
            # needs more points than its own order to be determined.
            length = min(max(int(window), _MIN_MEDIAN_POINTS), count)
            if length % 2 == 0:
                length -= 1
            polyorder = min(max(int(order), 1), length - 1)
            if length < _MIN_MEDIAN_POINTS:
                return list(values)
            smoothed = savgol_filter(filled, length, polyorder)
        else:
            # filtfilt runs the filter forwards and back, so the result
            # has no phase shift — a smoothed peak stays where it was.
            # It needs a few times the filter length in samples.
            filter_order = min(
                max(int(order), BUTTER_ORDER_BOUNDS[0]), BUTTER_ORDER_BOUNDS[1]
            )
            if count <= (_FILTFILT_MIN_LENGTH_MULTIPLE * (filter_order + 1)):
                return list(values)
            normalized = min(
                max(float(cutoff), BUTTER_CUTOFF_BOUNDS[0]), BUTTER_CUTOFF_BOUNDS[1]
            )
            numerator, denominator = butter(filter_order, normalized, btype="low")
            smoothed = filtfilt(numerator, denominator, filled)
    except Exception:
        return list(values)
    return _restore_gaps([float(value) for value in smoothed], gaps)


def smoothed_series(
    series, method, window=SAVGOL_WINDOW_PTS, order=SAVGOL_ORDER, cutoff=BUTTER_CUTOFF
):
    """``series`` with every curve smoothed by ``method``."""
    if method not in ("savgol", "butterworth"):
        return series
    logger.debug(
        f"Smoothing {len(series)} curves for display: {method}"
        + (
            f" window={window} order={order}"
            if method == "savgol"
            else f" order={order} cutoff={cutoff:g} of Nyquist"
        )
    )
    return {
        roi_id: (name, elapsed, smoothed_values(values, method, window, order, cutoff))
        for roi_id, (name, elapsed, values) in series.items()
    }


def analysed_series(session, filtered_paths, visible_only=True):
    """(series, outlier flags): everything a fit sees, in the order the
    corrections have to happen.

    Outliers go first. A spike inside a reference ROI would otherwise
    be subtracted from every curve before anything tested it — and once
    spread across them all, the per-curve test cannot find it. For the
    same reason it precedes the baseline shift and the normalisation,
    either of which one wild point would otherwise define.

    Smoothing is NOT here: it is a display aid, and a fit of a smoothed
    curve reports a goodness it did not earn.
    """
    figure = session.figure
    series = derive_series(session, filtered_paths)
    flags = {}
    steps = []
    if figure.remove_outliers:
        series, flags = without_outliers(
            series, figure.outlier_threshold, figure.outlier_window
        )
        dropped = sum(
            sum(1 for flag in roi_flags if flag) for roi_flags in flags.values()
        )
        steps.append(
            f"outliers({figure.outlier_threshold:g} MAD, "
            f"window {figure.outlier_window}) dropped "
            f"{dropped}"
        )
    if figure.subtract_background_ref:
        # After the outliers, before the visibility filter: the
        # references are the very curves a user hides once they are
        # flat, and reading the baseline from the filtered set would
        # let that click turn the correction off.
        series = background_ref_corrected_series(session, series)
        steps.append(
            f"background-ref({sum(1 for roi in session.rois if roi.is_background_ref)} "
            f"marked)"
        )
    if visible_only:
        series = visible_series(session, series)
    if figure.subtract_first:
        series = subtracted_series(series)
        steps.append("subtract-first")
    if figure.normalize:
        series = normalized_series(series)
        steps.append("normalise")
    logger.debug(
        f"Series for {len(series)} ROIs over {len(filtered_paths)} "
        f"images, stat={session.plot_stat}"
        + (f"; {'; '.join(steps)}" if steps else "; no corrections")
    )
    return series, flags

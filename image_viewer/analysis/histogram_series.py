# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Histogram view's maths over the pixels each ROI measures: the
shared bins (clipped, linear or logarithmic), the per-ROI counts (raw
or as a fraction of the ROI), their Savitzky-Golay smoothing over the
bins, and the distribution fitted to each ROI's pixels with its curve
scaled onto the histogram. Qt-free; the plot pane only draws."""

# Standard library imports.
import math

# Third-party imports.
import numpy as np
from scipy import stats

# Local imports.
from .consts import HISTOGRAM_FIT_MIN_PIXELS
from .plot_series import smoothed_values


def histogram_edges(samples, bins, clip_percent=0.0, log=False):
    """Bin edges shared by every sample in ``samples`` (1-D pixel
    arrays), so the ROIs compare bin for bin: ``bins`` bins over the
    pooled pixels' range less ``clip_percent`` of them off each tail —
    evenly spaced, or with ``log`` geometrically spaced over the
    positive pixels, so every bin is as wide on a log axis.

    None when there is nothing to bin: no pixels, or with ``log`` none
    above zero. A range of one value is widened about it, as numpy
    does, so the bins still have width."""
    pooled = np.concatenate([np.asarray(sample, dtype=float) for sample in samples])
    pooled = pooled[np.isfinite(pooled)]

    if log:
        pooled = pooled[pooled > 0]

    if not pooled.size:
        return None

    low, high = np.percentile(pooled, (clip_percent, 100.0 - clip_percent))

    if log:
        if high <= low:
            low, high = low / 2.0, high * 2.0

        return np.geomspace(low, high, int(bins) + 1)

    if high <= low:
        low, high = low - 0.5, high + 0.5

    return np.linspace(low, high, int(bins) + 1)


def bin_centres(edges, log=False):
    """Where each bin's count is drawn when the outline is a line:
    midway across it on the axis it is spaced for — the arithmetic
    centre of an even bin, the geometric one of a logarithmic bin."""
    if log:
        return np.sqrt(edges[:-1] * edges[1:])

    return (edges[:-1] + edges[1:]) / 2.0


def in_range(pixels, low, high):
    """The pixels from ``low`` to ``high``, both included — those the
    intensity filter keeps, or those inside the binned range, which a
    clip did not trim away."""
    return pixels[(pixels >= low) & (pixels <= high)]


def bins_within(counts, low, high):
    """Which bins' heights lie from ``low`` to ``high``, both included —
    in the counts' own unit, pixels or fractions of the ROI."""
    return (counts >= low) & (counts <= high)


def pixels_in_bins(pixels, edges, selected):
    """The pixels falling in the bins of ``edges`` that ``selected``
    marks — binned as np.histogram bins them, the last bin closed on
    the right; pixels outside the edges fall in none."""
    inside = (pixels >= edges[0]) & (pixels <= edges[-1])
    bins = np.clip(
        np.searchsorted(edges, pixels, side="right") - 1, 0, len(selected) - 1
    )

    return pixels[inside & selected[bins]]


def histogram_counts(pixels, edges, normalize=False):
    """Pixels per bin of ``edges``, or with ``normalize`` the fraction
    of ALL the ROI's pixels per bin — clipped tails included in the
    whole, so a fraction means the same whatever the clip — letting
    ROIs of different sizes compare."""
    counts = np.histogram(pixels, edges)[0].astype(float)

    if normalize and pixels.size:
        counts /= pixels.size

    return counts


def smoothed_counts(counts, window, order):
    """``counts`` smoothed by Savitzky-Golay over the bins — ``window``
    in bins — with the time series' own filter, so a too-short run is
    returned as it is. Clamped at zero: the polynomial can dip below
    it in a sparse tail, and no bin holds fewer than no pixels."""
    smoothed = smoothed_values(list(counts), "savgol", window, order)

    return np.clip(np.asarray(smoothed, dtype=float), 0.0, None)


def fit_distribution(pixels, kind):
    """(frozen scipy distribution, legend text) for ``kind`` —
    "normal" or "lognormal" — fitted to ``pixels`` by maximum
    likelihood, or None when it cannot be: fewer than
    HISTOGRAM_FIT_MIN_PIXELS pixels, no spread, a log-normal over any
    pixel at or below zero, or a non-finite estimate.

    The log-normal is fitted with its location pinned at 0, so its μ
    and σ are the mean and standard deviation of ln(intensity) and its
    median is e^μ."""
    values = np.asarray(pixels, dtype=float)

    if values.size < HISTOGRAM_FIT_MIN_PIXELS:
        return None

    if kind == "normal":
        mean, spread = stats.norm.fit(values)
        distribution = stats.norm(loc=mean, scale=spread)
        label = f"N(μ={mean:.4g}, σ={spread:.3g})"
    elif kind == "lognormal":
        if values.min() <= 0:
            return None

        spread, _location, scale = stats.lognorm.fit(values, floc=0)
        mean = math.log(scale) if scale > 0 else math.nan
        distribution = stats.lognorm(s=spread, scale=scale)
        label = f"logN(μ={mean:.4g}, σ={spread:.3g})"
    else:
        return None

    if not (math.isfinite(mean) and math.isfinite(spread) and spread > 0):
        return None

    return distribution, label


def fitted_counts(distribution, edges, count, samples, log=False, floor=0.0):
    """(x, y) of ``distribution`` drawn over the histogram of ``edges``
    at ``samples`` points: the pixels a bin at x is expected to hold
    out of ``count`` — the density times the bin's width there, which
    is constant for even bins and grows with x for logarithmic ones.
    ``count`` is in the histogram's own unit: the fitted pixels, or
    their fraction of the ROI when it is normalised. Below ``floor``
    (in that unit too) y is NaN, so the curve breaks off there."""
    bins = len(edges) - 1

    if log:
        x_values = np.geomspace(edges[0], edges[-1], samples)
        widths = x_values * math.log(edges[-1] / edges[0]) / bins
    else:
        x_values = np.linspace(edges[0], edges[-1], samples)
        widths = (edges[-1] - edges[0]) / bins

    y_values = count * distribution.pdf(x_values) * widths

    return x_values, np.where(y_values >= floor, y_values, np.nan)

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Histogram view's maths: shared bins (clipped, linear or log),
counts and their normalisation, Savitzky-Golay over the bins, and the
distribution fits recovering known parameters."""

# Standard library imports.
import math

# Third-party imports.
import numpy as np
import pytest

# Microdrop package imports.
from image_viewer.analysis.consts import HISTOGRAM_FIT_MIN_PIXELS
from image_viewer.analysis.histogram_series import (
    bin_centres,
    bins_within,
    fit_distribution,
    fitted_counts,
    histogram_counts,
    histogram_edges,
    in_range,
    pixels_in_bins,
    smoothed_counts,
)

#: A seeded generator, so every run draws the same samples.
RNG_SEED = 7


@pytest.fixture
def rng():
    return np.random.default_rng(RNG_SEED)


def test_edges_span_the_pooled_range(rng):
    first = rng.normal(100.0, 5.0, 500)
    second = rng.normal(300.0, 5.0, 200)

    edges = histogram_edges([first, second], 64)

    assert len(edges) == 65
    assert edges[0] == pytest.approx(min(first.min(), second.min()))
    assert edges[-1] == pytest.approx(max(first.max(), second.max()))
    assert np.allclose(np.diff(edges), np.diff(edges)[0])


def test_clip_trims_hot_pixels_off_the_range(rng):
    pixels = np.concatenate([rng.normal(500.0, 10.0, 10_000), [60_000.0, 65_000.0]])

    edges = histogram_edges([pixels], 32, clip_percent=1.0)

    assert edges[0] == pytest.approx(np.percentile(pixels, 1.0))
    assert edges[-1] == pytest.approx(np.percentile(pixels, 99.0))
    assert edges[-1] < 1_000.0
    assert in_range(pixels, edges[0], edges[-1]).size < pixels.size


def test_log_edges_are_geometric_over_the_positive_pixels():
    pixels = np.array([-5.0, 0.0, 1.0, 10.0, 100.0])

    edges = histogram_edges([pixels], 2, log=True)

    assert edges == pytest.approx([1.0, 10.0, 100.0])
    assert bin_centres(edges, log=True) == pytest.approx(
        [math.sqrt(10.0), math.sqrt(1000.0)]
    )
    assert histogram_edges([np.array([-1.0, 0.0])], 8, log=True) is None


def test_a_single_value_still_gets_bins_with_width():
    edges = histogram_edges([np.full(20, 7.0)], 4)

    assert edges[0] < 7.0 < edges[-1]
    assert histogram_counts(np.full(20, 7.0), edges).sum() == 20


def test_no_pixels_means_no_edges():
    assert histogram_edges([np.array([])], 16) is None


def test_normalize_turns_counts_into_fractions_of_the_roi(rng):
    pixels = rng.normal(200.0, 20.0, 4_000)
    edges = histogram_edges([pixels], 40)

    counts = histogram_counts(pixels, edges)
    fractions = histogram_counts(pixels, edges, normalize=True)

    assert counts.sum() == pixels.size
    assert fractions.sum() == pytest.approx(1.0)
    assert fractions == pytest.approx(counts / pixels.size)


def test_normalized_fractions_count_clipped_tails_in_the_whole(rng):
    pixels = rng.normal(200.0, 20.0, 4_000)
    edges = histogram_edges([pixels], 40, clip_percent=5.0)

    fractions = histogram_counts(pixels, edges, normalize=True)

    assert fractions.sum() == pytest.approx(
        in_range(pixels, edges[0], edges[-1]).size / pixels.size
    )
    assert fractions.sum() < 1.0


def test_savgol_over_bins_keeps_the_shape_and_roughly_the_sum(rng):
    pixels = rng.normal(200.0, 20.0, 2_000)
    counts = histogram_counts(pixels, histogram_edges([pixels], 60))

    smoothed = smoothed_counts(counts, 9, 2)

    assert smoothed.shape == counts.shape
    assert smoothed.min() >= 0.0
    assert smoothed.sum() == pytest.approx(counts.sum(), rel=0.05)
    # Smoother: the bin-to-bin jitter shrinks.
    assert np.abs(np.diff(smoothed)).sum() < np.abs(np.diff(counts)).sum()


def test_savgol_leaves_a_run_too_short_for_its_window_alone():
    counts = np.array([1.0, 4.0])

    assert smoothed_counts(counts, 9, 2) == pytest.approx(counts)


def test_normal_fit_recovers_its_parameters(rng):
    pixels = rng.normal(812.0, 21.0, 20_000)

    distribution, label = fit_distribution(pixels, "normal")

    assert distribution.mean() == pytest.approx(812.0, rel=0.01)
    assert distribution.std() == pytest.approx(21.0, rel=0.05)
    assert label.startswith("N(μ=")


def test_lognormal_fit_recovers_its_parameters(rng):
    pixels = rng.lognormal(mean=6.5, sigma=0.3, size=20_000)

    distribution, label = fit_distribution(pixels, "lognormal")

    assert math.log(distribution.median()) == pytest.approx(6.5, rel=0.01)
    assert distribution.kwds["s"] == pytest.approx(0.3, rel=0.05)
    assert label.startswith("logN(μ=")


@pytest.mark.parametrize(
    "pixels, kind",
    [
        (np.arange(HISTOGRAM_FIT_MIN_PIXELS - 1, dtype=float) + 1.0, "normal"),
        (np.full(50, 9.0), "normal"),
        (np.linspace(0.0, 10.0, 50), "lognormal"),
        (np.linspace(-1.0, 10.0, 50), "lognormal"),
        (np.linspace(1.0, 10.0, 50), "unknown"),
    ],
)
def test_a_fit_that_cannot_be_made_returns_none(pixels, kind):
    assert fit_distribution(pixels, kind) is None


def test_fitted_counts_match_the_histogram_they_are_drawn_over(rng):
    pixels = rng.normal(500.0, 30.0, 50_000)
    edges = histogram_edges([pixels], 50)
    counts = histogram_counts(pixels, edges)
    distribution, _label = fit_distribution(pixels, "normal")

    x_values, y_values = fitted_counts(distribution, edges, pixels.size, 200)

    # The curve's peak is the tallest bin's height, near enough.
    assert x_values[0] == pytest.approx(edges[0])
    assert x_values[-1] == pytest.approx(edges[-1])
    assert y_values.max() == pytest.approx(counts.max(), rel=0.1)


def test_fitted_counts_on_log_bins_scale_with_the_bin_width(rng):
    pixels = rng.lognormal(mean=6.0, sigma=0.5, size=50_000)
    edges = histogram_edges([pixels], 50, log=True)
    counts = histogram_counts(pixels, edges)
    distribution, _label = fit_distribution(pixels, "lognormal")

    _x_values, y_values = fitted_counts(distribution, edges, pixels.size, 400, log=True)

    assert y_values.max() == pytest.approx(counts.max(), rel=0.1)


def test_fitted_counts_break_off_below_the_floor():
    distribution, _label = fit_distribution(np.linspace(-3.0, 3.0, 1_001), "normal")
    edges = np.linspace(-20.0, 20.0, 41)

    _x_values, y_values = fitted_counts(distribution, edges, 1_000.0, 101, floor=0.5)

    assert np.isnan(y_values[0]) and np.isnan(y_values[-1])
    assert np.nanmin(y_values) >= 0.5


def test_the_intensity_range_drops_pixels_before_binning(rng):
    background = rng.normal(50.0, 5.0, 3_000)
    droplet = rng.normal(800.0, 20.0, 1_000)
    pixels = np.concatenate([background, droplet])

    kept = in_range(pixels, 400.0, 2_000.0)
    edges = histogram_edges([kept], 32)

    assert kept.size == 1_000
    assert edges[0] > 400.0
    assert histogram_counts(kept, edges).sum() == kept.size
    assert histogram_counts(kept, edges, normalize=True).sum() == pytest.approx(1.0)


def test_the_count_range_selects_the_pixels_of_the_bins_it_keeps():
    # Bin heights 1, 3, 5 and 2 over the bins [0, 1), [1, 2), [2, 3), [3, 4].
    pixels = np.array([0.5, 1.2, 1.5, 1.8, 2.1, 2.3, 2.5, 2.7, 2.9, 3.4, 4.0])
    edges = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    counts = histogram_counts(pixels, edges)

    selected = bins_within(counts, 2.0, 4.0)
    fitted = pixels_in_bins(pixels, edges, selected)

    assert counts == pytest.approx([1.0, 3.0, 5.0, 2.0])
    assert selected.tolist() == [False, True, False, True]
    # The right edge belongs to the last bin, as np.histogram has it.
    assert fitted.tolist() == [1.2, 1.5, 1.8, 3.4, 4.0]
    assert pixels_in_bins(np.array([-1.0, 5.0]), edges, selected).size == 0


def test_too_few_pixels_in_the_count_range_leave_no_fit(rng):
    pixels = rng.normal(500.0, 30.0, 5_000)
    edges = histogram_edges([pixels], 64)
    counts = histogram_counts(pixels, edges)

    # Only the sparsest tail bins, a handful of pixels between them.
    selected = bins_within(counts, 1.0, 1.0)
    fitted = pixels_in_bins(pixels, edges, selected)

    assert fitted.size < HISTOGRAM_FIT_MIN_PIXELS
    assert fit_distribution(fitted, "normal") is None
    assert fit_distribution(pixels_in_bins(pixels, edges, counts > 0), "normal")

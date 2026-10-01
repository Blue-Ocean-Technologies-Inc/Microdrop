# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the Qt-free curve-fitting core."""

# Standard library imports.
import math

# Third-party imports.
import numpy as np

# Microdrop package imports.
from image_viewer.analysis.curve_fit import (
    fastest_change_time,
    fit_series,
    second_derivative_extrema,
    trimmed_note,
)


def test_linear_fit_recovers_slope_and_intercept():
    t = np.linspace(0.0, 10.0, 20)
    fit = fit_series(t, 3.0 * t + 5.0, "linear")
    assert abs(fit.params["c1"] - 3.0) < 1e-6
    assert abs(fit.params["c0"] - 5.0) < 1e-6
    assert fit.r_squared > 0.999999
    assert fit.equation.startswith("y = 3·t")


def test_quadratic_and_cubic_recover_coefficients():
    t = np.linspace(-5.0, 5.0, 30)
    quadratic = fit_series(t, 2.0 * t**2 - 3.0 * t + 1.0, "poly2")
    assert abs(quadratic.params["c2"] - 2.0) < 1e-6
    assert abs(quadratic.params["c1"] + 3.0) < 1e-6
    assert abs(quadratic.params["c0"] - 1.0) < 1e-6
    cubic = fit_series(t, 0.5 * t**3 + t, "poly3")
    assert abs(cubic.params["c3"] - 0.5) < 1e-6
    assert abs(cubic.params["c1"] - 1.0) < 1e-6


def test_exponential_fit_recovers_decay():
    t = np.linspace(0.0, 20.0, 40)
    fit = fit_series(t, 100.0 * np.exp(-0.3 * t) + 10.0, "exponential")
    assert abs(fit.params["amplitude"] - 100.0) / 100.0 < 0.05
    assert abs(fit.params["rate"] + 0.3) / 0.3 < 0.05
    assert abs(fit.params["offset"] - 10.0) / 10.0 < 0.05
    assert fit.r_squared > 0.999
    assert "e^(" in fit.equation


def test_nan_pairs_are_filtered():
    t = np.linspace(0.0, 10.0, 20)
    values = 3.0 * t + 5.0
    values[3] = math.nan
    values[15] = math.nan
    fit = fit_series(t, values, "linear")
    assert abs(fit.params["c1"] - 3.0) < 1e-6


def test_too_few_points_and_none_method_return_none():
    assert fit_series([0.0, 1.0], [1.0, 2.0], "exponential") is None
    assert fit_series([0.0], [1.0], "linear") is None
    assert fit_series([0.0, 1.0, 2.0], [1.0, 2.0, 3.0], "none") is None


def test_flat_second_derivative_yields_no_extrema():
    t = np.linspace(0.0, 10.0, 20)
    fit = fit_series(t, 3.0 * t + 5.0, "linear")
    assert second_derivative_extrema(fit, 0.0, 10.0) == {}


def test_cubic_second_derivative_extrema_at_span_edges():
    t = np.linspace(-2.0, 2.0, 40)
    fit = fit_series(t, t**3, "poly3")
    extrema = second_derivative_extrema(fit, -2.0, 2.0)
    t_max, y_max = extrema["max"]
    t_min, y_min = extrema["min"]
    assert abs(t_max - 2.0) < 1e-6  # d2 = 6t: max at right edge
    assert abs(t_min + 2.0) < 1e-6  # ...min at left edge
    assert abs(y_max - 8.0) < 1e-3  # y on the fitted curve (t^3)
    assert abs(y_min + 8.0) < 1e-3


def test_flat_data_linear_fit_has_r_squared_one():
    t = np.linspace(0.0, 10.0, 10)
    fit = fit_series(t, np.full_like(t, 7.0), "linear")
    assert fit.r_squared == 1.0


def test_sigmoid_recovers_known_params():
    t = np.arange(0.0, 200.0, 10.0)
    y = 3000.0 / (1.0 + np.exp(-0.08 * (t - 95.0))) + 500.0
    fit = fit_series(t, y, "sigmoid")
    assert fit is not None
    assert fit.r_squared > 0.999
    assert abs(fit.params["rate"] - 0.08) < 0.008
    assert abs(fit.params["midpoint"] - 95.0) < 2.0
    # Both plateaus are reported, not an amplitude hiding the far one
    # behind a sum: the curve runs from 500 up to 3500.
    assert abs(fit.params["initial"] - 500.0) < 75.0
    assert abs(fit.params["final"] - 3500.0) < 150.0
    assert fit.equation.startswith("y = ")
    assert "e^(-" in fit.equation


def test_sigmoid_canonicalizes_negative_rate():
    # A falling sigmoid must still report a positive rate (fitted
    # asymptotes swapped, since s(-x) == 1 - s(x)).
    t = np.arange(0.0, 200.0, 10.0)
    y = 3000.0 / (1.0 + np.exp(0.08 * (t - 95.0))) + 500.0
    fit = fit_series(t, y, "sigmoid")
    assert fit is not None
    assert fit.params["rate"] > 0
    assert fit.r_squared > 0.999


def test_first_derivative_linear_is_slope():
    t = np.arange(0.0, 100.0, 10.0)
    fit = fit_series(t, 5.0 * t + 600.0, "linear")
    assert np.allclose(fit.first_derivative([0.0, 50.0]), 5.0)


def test_first_derivative_exponential():
    t = np.arange(0.0, 200.0, 10.0)
    fit = fit_series(t, 3000.0 * np.exp(-0.05 * t) + 500.0, "exponential")
    # dy/dt at 0 is A*k = -150
    assert abs(float(fit.first_derivative(0.0)) + 150.0) < 5.0


def test_fastest_change_sigmoid_at_inflection():
    t = np.arange(0.0, 200.0, 10.0)
    y = 3000.0 / (1.0 + np.exp(-0.08 * (t - 95.0))) + 500.0
    fit = fit_series(t, y, "sigmoid")
    assert abs(fastest_change_time(fit, 0.0, 190.0) - 95.0) < 1.0


def test_fastest_change_linear_is_suppressed():
    t = np.arange(0.0, 100.0, 10.0)
    fit = fit_series(t, 5.0 * t + 600.0, "linear")
    assert fastest_change_time(fit, 0.0, 90.0) is None


def test_fastest_change_uses_the_fitted_inflection_exactly():
    # Not the nearest sample of the search grid: the sigmoid knows its
    # own inflection, so the bar reads the fitted midpoint.
    t = np.arange(0.0, 200.0, 10.0)
    y = 3000.0 / (1.0 + np.exp(-0.08 * (t - 95.0))) + 500.0
    fit = fit_series(t, y, "sigmoid")
    assert fastest_change_time(fit, 0.0, 190.0) == fit.params["midpoint"]


def test_fastest_change_falls_back_when_inflection_is_outside():
    # Fitted on the rise alone, the inflection sits past the window;
    # inside it the rate only grows, so the window edge is the answer.
    t = np.arange(0.0, 60.0, 5.0)
    y = 3000.0 / (1.0 + np.exp(-0.08 * (t - 95.0))) + 500.0
    fit = fit_series(t, y, "sigmoid")
    assert fit.params["midpoint"] > 55.0
    assert abs(fastest_change_time(fit, 0.0, 55.0) - 55.0) < 1e-6


def _bleached_series():
    """A clean sigmoid (inflection at 95 s) whose plateau then decays,
    as photobleaching does — the 4PL misfits and reports the crossing
    early unless the tail is dropped."""
    t = np.arange(0.0, 200.0, 10.0)
    rise = 3000.0 / (1.0 + np.exp(-0.08 * (t - 95.0))) + 500.0
    return t, rise * np.exp(-0.015 * np.maximum(t - 120.0, 0.0))


def test_bleached_tail_biases_the_inflection_when_kept():
    t, y = _bleached_series()
    fit = fit_series(t, y, "sigmoid")
    assert fit.r_squared < 0.99
    assert fit.params["midpoint"] < 90.0  # dragged early
    assert fit.fitted_end == t[-1]  # nothing dropped


def test_trim_tail_refits_on_the_leading_slice():
    t, y = _bleached_series()
    fit = fit_series(t, y, "sigmoid", trim_tail=True)
    assert fit.r_squared >= 0.99
    assert fit.fitted_start == t[0] and fit.fitted_end < t[-1]
    assert abs(fit.params["midpoint"] - 95.0) < 5.0
    # The bar reports the inflection over the whole series, not the
    # edge of the shorter span the fit was solved on.
    assert fastest_change_time(fit, t[0], t[-1]) == fit.params["midpoint"]


def test_trim_tail_keeps_the_full_fit_when_trimming_cannot_reach_target():
    # Pure noise never reaches R² 0.99, so the untrimmed fit stands.
    t = np.arange(0.0, 200.0, 10.0)
    y = np.random.default_rng(1).normal(500.0, 50.0, size=t.shape)
    fit = fit_series(t, y, "poly3", trim_tail=True)
    assert fit is not None
    assert fit.fitted_end == t[-1]


def test_trim_tail_leaves_a_good_fit_alone():
    t = np.arange(0.0, 200.0, 10.0)
    y = 3000.0 / (1.0 + np.exp(-0.08 * (t - 95.0))) + 500.0
    fit = fit_series(t, y, "sigmoid", trim_tail=True)
    assert fit.fitted_end == t[-1]
    assert trimmed_note(fit, t[-1]) == ""


def test_trimmed_note_reports_the_domain_actually_fitted():
    t, y = _bleached_series()
    fit = fit_series(t, y, "sigmoid", trim_tail=True)
    note = trimmed_note(fit, t[-1])
    assert note.startswith(" (fit to t ≤ ")
    assert f"{fit.fitted_end:.4g}" in note


def test_fastest_change_exponential_decay_at_start():
    t = np.arange(0.0, 200.0, 10.0)
    fit = fit_series(t, 3000.0 * np.exp(-0.05 * t) + 500.0, "exponential")
    assert abs(fastest_change_time(fit, 0.0, 190.0)) < 1.0

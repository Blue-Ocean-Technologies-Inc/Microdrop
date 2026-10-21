# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the custom fit and the preset store."""

# Standard library imports.
import warnings

# Third-party imports.
import numpy as np

# Microdrop package imports.
from image_viewer.analysis.curve_fit import (
    FIT_TEMPLATES,
    fit_series,
    user_seed,
)
from image_viewer.analysis.fit_presets import (
    add_preset,
    choices_for,
    expression_for,
    load_presets,
    method_for_expression,
    method_label,
    save_presets,
    solving_method,
)

# Microdrop utils imports.
from microdrop_utils.expression import parse_expression


def test_a_custom_fit_recovers_the_parameters_it_was_generated_from():
    t = np.linspace(0.0, 200.0, 60)
    y = 100.0 + 800.0 / (1.0 + np.exp(-0.06 * (t - 95.0)))
    fit = fit_series(t, y, "custom", expression="a + b/(1 + exp(-c*(x - d)))")
    assert fit.r_squared > 0.9999
    assert abs(fit.params["a"] - 100.0) < 1.0
    assert abs(fit.params["b"] - 800.0) < 1.0
    assert abs(fit.params["c"] - 0.06) < 0.001
    assert abs(fit.params["d"] - 95.0) < 1.0
    assert fit.equation.startswith("y = ")


def test_a_decay_is_fitted_despite_having_no_natural_seed():
    # The seed ladder exists for this: a rate seeded at 1.0 overflows
    # and one seeded at 0.0 has no gradient, so only the -1/span seed
    # finds it — and a bleaching series is exactly this shape.
    t = np.linspace(0.0, 200.0, 60)
    y = 5.0 * np.exp(-0.02 * t) + 2.0
    fit = fit_series(t, y, "custom", expression="a*exp(b*x) + c")
    assert fit.r_squared > 0.9999
    assert abs(fit.params["b"] + 0.02) < 0.001


def test_numeric_derivatives_track_the_analytic_ones():
    t = np.linspace(0.0, 200.0, 60)
    y = 100.0 + 800.0 / (1.0 + np.exp(-0.06 * (t - 95.0)))
    custom = fit_series(t, y, "custom", expression="a + b/(1 + exp(-c*(x - d)))")
    builtin = fit_series(t, y, "sigmoid")
    grid = np.linspace(0.0, 200.0, 25)
    assert np.allclose(
        custom.first_derivative(grid), builtin.first_derivative(grid), atol=1e-3
    )
    assert np.allclose(
        custom.second_derivative(grid), builtin.second_derivative(grid), atol=1e-5
    )


def test_an_unusable_equation_fits_nothing_rather_than_raising():
    t = np.linspace(0.0, 10.0, 20)
    assert fit_series(t, t, "custom", expression="a + ") is None
    assert fit_series(t, t, "custom", expression="") is None
    # Fewer points than parameters says nothing about any of them.
    assert (
        fit_series([0.0, 1.0], [1.0, 2.0], "custom", expression="a + b*x + c*x^2")
        is None
    )


def test_every_built_in_template_parses_and_names_its_own_parameters():
    t = np.linspace(1.0, 200.0, 60)
    y = 100.0 + 800.0 / (1.0 + np.exp(-0.06 * (t - 95.0)))
    for method, template in FIT_TEMPLATES.items():
        expression = parse_expression(template)
        fit = fit_series(t, y, method)
        assert list(fit.params) == expression.parameters, method


def test_presets_round_trip_through_their_json():
    presets = [("Bleach", "a*exp(-b*x) + c"), ("Melt", "a + b*x")]
    assert load_presets(save_presets(presets)) == presets


def test_unreadable_preset_json_is_no_presets():
    assert load_presets("") == []
    assert load_presets("[not json") == []
    assert load_presets('{"not": "a list"}') == []
    assert load_presets('[{"name": "x"}]') == []
    # An entry that no longer parses is dropped rather than offered.
    assert load_presets('[{"name": "x", "expression": "a + "}]') == []


def test_adding_a_preset_replaces_one_of_the_same_name():
    presets = add_preset([], "Bleach", "a*exp(-b*x)")
    presets = add_preset(presets, "Melt", "a + b*x")
    presets = add_preset(presets, "Bleach", "a*exp(-b*x) + c")
    assert presets == [("Melt", "a + b*x"), ("Bleach", "a*exp(-b*x) + c")]


def test_an_equation_already_offered_is_not_addable_again():
    presets = [("Bleach", "a*exp(-b*x) + c")]
    assert method_for_expression("a*exp(-b*x) + c", presets) == "preset:Bleach"
    # Whitespace is not a different equation.
    assert method_for_expression("a*exp(-b*x)+c", presets) == "preset:Bleach"
    assert method_for_expression(FIT_TEMPLATES["sigmoid"], []) == "sigmoid"
    assert method_for_expression("q*x + w", presets) == ""


def test_a_preset_is_solved_as_a_custom_equation():
    presets = [("Bleach", "a*exp(-b*x) + c")]
    assert solving_method("preset:Bleach") == "custom"
    assert solving_method("sigmoid") == "sigmoid"
    assert expression_for("preset:Bleach", presets) == "a*exp(-b*x) + c"
    assert expression_for("sigmoid", presets) == FIT_TEMPLATES["sigmoid"]
    assert expression_for("custom", presets, "a*x") == "a*x"
    assert expression_for("none", presets) == ""
    assert method_label("preset:Bleach", presets) == "Bleach"
    assert method_label("sigmoid", presets) == "Sigmoid"


def test_a_deleted_preset_stays_selectable():
    # An experiment saved against a preset since removed must not have
    # its stored method silently swapped for another.
    choices = choices_for([], current="preset:Gone")
    assert choices[-1] == "preset:Gone"
    assert expression_for("preset:Gone", []) == ""


def test_starting_values_are_all_or_nothing():
    # A seed is a vector: filling the gaps with invented numbers would
    # be a different starting point than the one that was asked for.
    assert user_seed(["a", "b"], {"a": 1.0, "b": 2.0}) == [1.0, 2.0]
    assert user_seed(["b", "a"], {"a": 1.0, "b": 2.0}) == [2.0, 1.0]
    assert user_seed(["a", "b"], {"a": 1.0}) is None
    assert user_seed(["a"], {}) is None
    assert user_seed(["a"], None) is None
    assert user_seed(["a"], {"a": "nonsense"}) is None
    assert user_seed(["a"], {"a": float("inf")}) is None


def test_starting_values_steer_a_fit_the_automatic_seeds_miss():
    # Two plateaus an order of magnitude apart: the uniform ladder has
    # no seed near both, and the user's do.
    t = np.linspace(0.0, 100.0, 40)
    y = 0.002 + 5000.0 / (1.0 + np.exp(-0.5 * (t - 50.0)))
    expression = "a + b/(1 + exp(-c*(x - d)))"
    guided = fit_series(
        t,
        y,
        "custom",
        expression=expression,
        initial_guesses={"a": 0.0, "b": 5000.0, "c": 0.5, "d": 50.0},
    )
    assert guided.r_squared > 0.9999
    assert not guided.auto_seeded
    assert abs(guided.params["d"] - 50.0) < 1.0


def test_a_poor_but_usable_start_is_obeyed_rather_than_overridden():
    # The whole point of typing starting values is that they are used;
    # a bad fit from them is honest feedback, and its R² shows it.
    t = np.linspace(0.0, 200.0, 60)
    y = 100.0 + 800.0 / (1.0 + np.exp(-0.06 * (t - 95.0)))
    expression = "a + b/(1 + exp(-c*(x - d)))"
    poor = fit_series(
        t,
        y,
        "custom",
        expression=expression,
        initial_guesses={name: 1e12 for name in "abcd"},
    )
    automatic = fit_series(t, y, "custom", expression=expression)
    assert automatic.r_squared > 0.9999
    assert poor.r_squared < 0.5  # obeyed, not quietly replaced
    assert not poor.auto_seeded


def test_a_start_that_reaches_nothing_falls_back_and_says_so():
    t = np.linspace(1.0, 50.0, 30)
    y = 3.0 * np.log(t + 2.0)
    # b = -1e6 puts log() of a negative number at the initial point, so
    # the solver has no residuals to work from at all.
    fit = fit_series(
        t, y, "custom", expression="a*log(x + b)", initial_guesses={"a": 1.0, "b": -1e6}
    )
    assert fit.r_squared > 0.9999  # rescued by the ladder
    assert fit.auto_seeded  # and the popup reports it
    # Built-ins have their own seeding and ignore the guesses entirely.
    assert not fit_series(t, y, "linear", initial_guesses={"c1": 1e9}).auto_seeded


def test_an_overflowing_custom_fit_survives_warnings_as_errors():
    # A warning raised inside the evaluated equation must not abort the
    # solver's seed ladder.
    t = np.linspace(0.0, 200.0, 60)
    y = 5.0 * np.exp(-0.02 * t) + 2.0
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fit = fit_series(t, y, "custom", expression="a*exp(b*x) + c")
    assert fit.r_squared > 0.9999

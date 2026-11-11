# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the typed-equation parser."""

# Standard library imports.
import math
import warnings

# Third-party imports.
import numpy as np
import pytest

# Microdrop utils imports.
from microdrop_utils.expression import (
    FitExpressionError,
    function_error,
    invert_function,
    is_identity,
    is_valid,
    is_valid_function,
    parse_expression,
    parse_function,
)


def test_parameters_are_the_unknown_names_in_order_of_appearance():
    # Order is the column order in the table, so it has to be the
    # order they were written in and not a set's iteration order.
    assert parse_expression("z + y*exp(-w*x)").parameters == ["z", "y", "w"]
    assert parse_expression("a*x + a*x^2 + b").parameters == ["a", "b"]


def test_t_is_the_variable_as_well_as_x():
    assert parse_expression("a*t + b").parameters == ["a", "b"]


def test_caret_is_a_power_not_exclusive_or():
    expression = parse_expression("a*x^2")
    assert float(expression(3.0, 2.0)) == 18.0
    assert expression.display_text == "a*x^2"


def test_an_equation_may_be_written_with_its_label():
    assert parse_expression("F(x) = a*x + b").parameters == ["a", "b"]
    assert parse_expression("y = a*x").parameters == ["a"]


def test_the_expression_evaluates_over_an_array():
    expression = parse_expression("a + b*x")
    assert list(expression(np.array([0.0, 1.0, 2.0]), 1.0, 2.0)) == [1.0, 3.0, 5.0]


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("", "type an equation"),
        ("a + ", "could not read"),
        ("a.b", "attribute access"),
        ("a[0]", "indexing"),
        ("lambda x: x", "lambda"),
        ("a if x else b", "conditional"),
        ("sine(x)*a", "unknown function 'sine'"),
        ("exp*a", "'exp' is a function"),
        ("a > x", "comparison"),
        ("2*x + 1", "no parameters"),
        ("_a*x", "cannot be a parameter name"),
        ("a" * 600, "longer than"),
    ],
)
def test_unusable_equations_explain_themselves(text, fragment):
    with pytest.raises(FitExpressionError) as raised:
        parse_expression(text)
    assert fragment in str(raised.value)
    assert not is_valid(text)


def test_nothing_outside_the_equation_is_reachable():
    # The parse refuses the call, and even if it did not, eval runs
    # with no builtins to reach.
    with pytest.raises(FitExpressionError):
        parse_expression("__import__('os').system('echo hi')")
    with pytest.raises(FitExpressionError):
        parse_expression("open('x')*a")
    # A parameter that happens to be named like a builtin is just a
    # parameter, and takes the value it is fitted with.
    assert float(parse_expression("open*x")(2.0, 3.0)) == 6.0


def test_an_overflowing_expression_survives_warnings_as_errors():
    # Numpy issuing a warning from inside the evaluated equation sends
    # CPython's warnings machinery looking for __import__ in globals
    # that deliberately have none, which surfaced as KeyError rather
    # than anything a caller could handle.
    expression = parse_expression("a*exp(b*x)")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = expression(np.array([0.0, 1e6]), 1.0, 1e6)
    assert not np.all(np.isfinite(result))


def test_a_function_of_x_has_no_parameters():
    f = parse_function("1.04*x^2/100 + 0.9*x + 1.2")
    assert f.parameters == []
    assert isinstance(f(10.0), float)
    assert f(10.0) == pytest.approx(1.04 + 9.0 + 1.2)
    assert f(np.array([0.0, 10.0])).shape == (2,)


def test_expected_and_t_are_the_variable_too():
    assert parse_function("2*expected")(3.0) == 6.0
    assert parse_function("2*t")(3.0) == 6.0


def test_a_constant_expression_is_rejected():
    for text in ("5", "1.2"):
        with pytest.raises(FitExpressionError, match="does not use x"):
            parse_function(text)

    assert function_error("1.2") == "the expression does not use x"


def test_an_unknown_name_is_named():
    with pytest.raises(FitExpressionError, match="unknown name 'a'"):
        parse_function("a*x")
    assert not is_valid_function("a*x")


def test_a_flipped_trend_names_the_direction():
    with pytest.raises(FitExpressionError) as raised:
        parse_function("expected = 0.96*actual - 1.1")
    assert "unknown name 'actual' — the compensation wants actual = f(expected)" in str(
        raised.value
    )


def test_an_expression_that_cannot_evaluate_is_invalid():
    for text in ("1/0 + x", "2**10000*x"):
        with pytest.raises(FitExpressionError, match="cannot evaluate"):
            parse_function(text)
        assert function_error(text).startswith("cannot evaluate")


@pytest.mark.parametrize(
    "text, x, value",
    [
        ("actual = 1.04·expected^2 + 0.9·expected + 1.2", 10.0, 104.0 + 9.0 + 1.2),
        ("y = 2×x", 3.0, 6.0),
        ("F(x) = x²", 3.0, 9.0),
        ("x³", 2.0, 8.0),
        ("actual = 1.2·e^(0.5·expected) + 3", 0.0, 4.2),
        ("1.04·x − 1.2", 10.0, 9.2),
    ],
)
def test_pasted_corner_text_parses_as_is(text, x, value):
    assert parse_function(text)(x) == pytest.approx(value)


def test_identity_is_empty_or_a_bare_variable():
    for text in ("", "  ", "x", "t", "expected", "actual = expected", "y = x"):
        assert is_identity(text)
    for text in ("x + 0", "2*x", "a"):
        assert not is_identity(text)


def test_function_error_is_empty_for_identity_and_valid_text():
    assert function_error("") == "" and function_error("x") == ""
    assert function_error("2*x + 1") == ""
    assert function_error("a*x") == "unknown name 'a'"
    with pytest.raises(FitExpressionError, match="type an expression of x"):
        parse_function("")


def test_the_fit_parser_still_collects_parameters():
    assert parse_expression("actual*x").parameters == ["actual"]
    assert parse_expression("y = a*x").parameters == ["a"]
    assert parse_expression("F(x) = a*x + b").parameters == ["a", "b"]
    with pytest.raises(FitExpressionError, match="no parameters"):
        parse_expression("2*x + 1")


@pytest.mark.parametrize("text", ["exp()", "exp(x, 1)", "exp(x, x)"])
def test_a_function_takes_exactly_one_argument(text):
    # A second positional argument is numpy's out=, which would write
    # the result into the caller's array.
    with pytest.raises(FitExpressionError, match=r"exp\(\) takes one argument"):
        parse_function(text)
    with pytest.raises(FitExpressionError, match=r"exp\(\) takes one argument"):
        parse_expression(f"a*{text}")


def test_function_error_reports_a_wrong_argument_count():
    assert function_error("exp()") == "exp() takes one argument"


def test_inverting_a_line():
    expected, missing = invert_function(parse_function("2*x + 1"), [21.0, 41.0])
    assert np.allclose(expected, [10.0, 20.0], atol=1e-6) and missing == 0


def test_a_quadratic_inverts_on_the_branch_nearest_identity():
    expected, _missing = invert_function(parse_function("x^2/100"), [25.0])  # ±50
    assert expected[0] == pytest.approx(50.0, abs=1e-6)


def test_the_spec_quadratic_round_trips():
    f = parse_function("1.04*x^2/100 + 0.9*x + 1.2")
    expected, _missing = invert_function(f, [f(60.0)])
    assert expected[0] == pytest.approx(60.0, abs=1e-6)


def test_inverting_an_exponential():
    f = parse_function("exp(x/50)")
    expected, _missing = invert_function(f, [math.exp(2.0)])
    assert expected[0] == pytest.approx(100.0, abs=1e-6)


def test_a_value_out_of_range_is_a_counted_gap():
    expected, missing = invert_function(parse_function("x^2/100"), [-5.0, 25.0])
    assert math.isnan(expected[0]) and missing == 1


def test_nan_in_stays_nan_and_is_not_counted():
    expected, missing = invert_function(parse_function("2*x"), [math.nan])
    assert math.isnan(expected[0]) and missing == 0


def test_non_finite_regions_of_f_are_skipped():
    f = parse_function("log(x)")
    expected, missing = invert_function(f, [0.0, math.log(1000.0)])
    assert expected[0] == pytest.approx(1.0, abs=1e-6)
    assert math.isnan(expected[1]) and missing == 1  # 1000 °C: outside the domain


def test_a_wider_domain_can_be_asked_for():
    f = parse_function("x")
    expected, _missing = invert_function(f, [600.0], domain=(0.0, 1000.0))
    assert expected[0] == pytest.approx(600.0)


def test_a_bracket_with_a_non_finite_interior_is_a_gap():
    # Finite at the grid points either side of the root, NaN between
    # them, where brentq refuses to continue.
    f = parse_function("x - 0.025 + 0*sqrt((x - 0.01)*(x - 0.04))")
    expected, missing = invert_function(f, [0.0])
    assert math.isnan(expected[0]) and missing == 1


def test_a_pole_is_not_a_root():
    expected, missing = invert_function(parse_function("1/(x - 0.025)"), [0.0])
    assert math.isnan(expected[0]) and missing == 1


def test_roots_on_the_domain_edges_are_found():
    expected, missing = invert_function(parse_function("x"), [-100.0, 500.0])
    assert expected.tolist() == [-100.0, 500.0] and missing == 0

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
import warnings

# Third-party imports.
import numpy as np
import pytest

# Microdrop utils imports.
from microdrop_utils.expression import (
    FitExpressionError,
    is_valid,
    parse_expression,
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

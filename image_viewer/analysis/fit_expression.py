# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""User-typed fit equations: parse ``a + b*exp(-c*x)`` into the list of
free parameters and a vectorized callable curve_fit can solve. Qt-free
and session-free, like the rest of the fitting code.

The text is walked with Python's own ``ast`` rather than split with a
regex, which is what lets an unusable equation come back as a sentence
("unknown function 'sine'") instead of a failed fit — and what keeps
anything that is not arithmetic (attributes, subscripts, lambdas,
calls to anything unlisted) from reaching the interpreter at all."""

# Standard library imports.
import ast

# Third-party imports.
import numpy as np
from scipy.special import erf, expit

#: Names that stand for the independent variable rather than a
#: parameter. The equations have always printed in t; the field asks
#: for F(x); both are accepted so neither reading is wrong.
VARIABLE_NAMES = ("x", "t")

#: Vectorized functions an equation may call.
FUNCTIONS = {
    "exp": np.exp,
    "log": np.log,
    "log10": np.log10,
    "sqrt": np.sqrt,
    "abs": np.abs,
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "asin": np.arcsin,
    "acos": np.arccos,
    "atan": np.arctan,
    "sinh": np.sinh,
    "cosh": np.cosh,
    "tanh": np.tanh,
    "expit": expit,
    "erf": erf,
}

#: Constants an equation may name.
CONSTANTS = {"pi": np.pi, "e": np.e}

#: Arithmetic an equation may use. Anything else — comparisons, bit
#: operations, the walrus — is rejected by name.
_BINARY_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
_UNARY_OPS = (ast.UAdd, ast.USub)

#: Longest equation accepted, a guard against pasting a file into the
#: field rather than a limit anyone types up against.
MAX_EXPRESSION_LENGTH = 500


class FitExpressionError(ValueError):
    """An equation that cannot be used, with a message written for the
    person who typed it."""


def _describe(node):
    """The offending construct, named the way a user would recognize
    it."""
    return {
        ast.Attribute: "attribute access",
        ast.Subscript: "indexing",
        ast.Lambda: "a lambda",
        ast.IfExp: "a conditional",
        ast.Compare: "a comparison",
        ast.BoolOp: "and/or",
        ast.List: "a list",
        ast.Dict: "a dict",
        ast.Tuple: "a tuple",
        ast.Starred: "*args",
    }.get(type(node), type(node).__name__)


def _check(node, parameters):
    """Walk one node, collecting parameter names in the order they are
    first seen, and refusing anything that is not arithmetic."""
    if isinstance(node, ast.Expression):
        _check(node.body, parameters)
    elif isinstance(node, ast.BinOp):
        if not isinstance(node.op, _BINARY_OPS):
            raise FitExpressionError(
                f"{type(node.op).__name__} is not allowed in an equation"
            )
        _check(node.left, parameters)
        _check(node.right, parameters)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _UNARY_OPS):
            raise FitExpressionError(
                f"{type(node.op).__name__} is not allowed in an equation"
            )
        _check(node.operand, parameters)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FitExpressionError("only plain functions can be called")
        if node.func.id not in FUNCTIONS:
            raise FitExpressionError(
                f"unknown function '{node.func.id}' — known ones are "
                f"{', '.join(sorted(FUNCTIONS))}"
            )
        if node.keywords:
            raise FitExpressionError(f"{node.func.id}() takes no keyword arguments")
        for argument in node.args:
            _check(argument, parameters)
    elif isinstance(node, ast.Name):
        name = node.id
        if name in VARIABLE_NAMES or name in CONSTANTS:
            return
        if name in FUNCTIONS:
            raise FitExpressionError(f"'{name}' is a function — write {name}(x)")
        if name.startswith("_"):
            raise FitExpressionError(f"'{name}' cannot be a parameter name")
        if name not in parameters:
            parameters.append(name)
    elif isinstance(node, ast.Constant):
        # Numbers only: a quoted string or a None is not arithmetic.
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FitExpressionError(f"{node.value!r} is not a number")
    else:
        raise FitExpressionError(f"{_describe(node)} is not allowed in an equation")


class FitExpression:
    """A parsed equation: its free parameters, in the order they first
    appear, and a vectorized callable of (x, *parameters)."""

    def __init__(self, text, parameters, code):
        self.text = text
        #: The same equation in the notation it was typed in — ^ is
        #: rewritten to ** to parse it, and reading it back out as **
        #: would not be what the user wrote.
        self.display_text = text.replace("**", "^")
        self.parameters = parameters
        self._code = code

    def __call__(self, x, *values):
        namespace = dict(FUNCTIONS)
        namespace.update(CONSTANTS)
        variable = np.asarray(x, dtype=float)
        for name in VARIABLE_NAMES:
            namespace[name] = variable
        namespace.update(zip(self.parameters, values))
        # Overflow and invalid values are routine here — an optimizer
        # tries parameters that put exp() past the float ceiling — and
        # the callers check whether the RESULT is finite. Silencing
        # them at the source also avoids a trap: numpy issuing a
        # warning from this frame sends CPython's warnings machinery
        # looking for __import__ in these globals, which raises
        # KeyError rather than any warning the caller could handle.
        #
        # No builtins: nothing outside the namespace above is reachable,
        # which the parse has already restricted to arithmetic anyway.
        with np.errstate(all="ignore"):
            return eval(self._code, {"__builtins__": {}}, namespace)


def parse_expression(text):
    """Parse a typed equation into a FitExpression. Raises
    FitExpressionError, whose message is meant to be shown as-is."""
    text = (text or "").strip()
    if not text:
        raise FitExpressionError("type an equation, e.g. a + b*exp(-c*x)")
    if len(text) > MAX_EXPRESSION_LENGTH:
        raise FitExpressionError(
            f"equation is longer than {MAX_EXPRESSION_LENGTH} characters"
        )
    # Both are how an equation is written rather than how Python spells
    # it; ^ is exclusive-or to the parser, and a leading "y =" or
    # "F(x) =" is the label around the expression, not part of it.
    text = text.replace("^", "**")
    for prefix in ("f(x)=", "f(t)=", "y=", "x=", "t="):
        stripped = text.replace(" ", "").lower()
        if stripped.startswith(prefix):
            text = text.split("=", 1)[1].strip()
            break
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as error:
        raise FitExpressionError(f"could not read the equation: {error.msg}") from error
    parameters = []
    _check(tree, parameters)
    if not parameters:
        raise FitExpressionError(
            "the equation has no parameters to fit — every symbol in it "
            "is either x or a known function"
        )
    return FitExpression(text, parameters, compile(tree, "<fit equation>", "eval"))


def is_valid(text):
    """True when ``text`` parses — for enabling a button without
    catching an exception at the call site."""
    try:
        parse_expression(text)
    except FitExpressionError:
        return False
    return True

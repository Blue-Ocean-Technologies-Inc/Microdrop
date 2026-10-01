# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Curve fitting for the ROI intensity series: pure math over
(elapsed, value) sequences — Qt-free, session-free. Each method yields
a FitResult carrying the equation text, R², a vectorized predictor,
and the analytic second derivative (for the curvature extremum
markers)."""

# Standard library imports.
import math
import re
import warnings

# Third-party imports.
import numpy as np
from scipy.optimize import curve_fit
from scipy.special import expit

# Enthought library imports.
from traits.api import Any, Bool, Dict, Float, HasTraits, Str

# Local imports.
from .fit_expression import FitExpressionError, parse_expression

#: Selectable fit models, in dropdown order ("none" = fitting off,
#: CUSTOM_METHOD = whatever equation the user typed).
CUSTOM_METHOD = "custom"
FIT_METHODS = ("none", "linear", "poly2", "poly3", "exponential", "sigmoid")

#: Human labels (fit dropdown + equations table).
FIT_LABELS = {
    "none": "No fit",
    "linear": "Linear",
    "poly2": "Quadratic",
    "poly3": "Cubic",
    "exponential": "Exponential",
    "sigmoid": "Sigmoid",
    CUSTOM_METHOD: "Custom",
}

#: What each built-in fits, in the notation the equation field uses —
#: so selecting one shows the form it will solve, and editing that text
#: carries straight over into a custom fit of the same shape.
#:
#: Each names the parameters that model actually reports, so the
#: equation on display and the table's columns say the same thing.
FIT_TEMPLATES = {
    "linear": "c1*x + c0",
    "poly2": "c2*x^2 + c1*x + c0",
    "poly3": "c3*x^3 + c2*x^2 + c1*x + c0",
    "exponential": "amplitude*exp(rate*x) + offset",
    "sigmoid": "initial + (final - initial)/(1 + exp(-rate*(x - midpoint)))",
}

#: Fewest finite points each model can be solved on.
_MIN_POINTS = {"linear": 2, "poly2": 3, "poly3": 4, "exponential": 4, "sigmoid": 5}

#: Constant initial guesses tried for a custom equation (see
#: _custom_seeds for the data-derived ones). All-zeros alone —
#: pyCftool's choice — stalls on a*exp(b*x), which has no gradient in
#: a at a = 0.
_CUSTOM_SEEDS = (1.0, 0.0)

#: Step for the numeric derivatives of a custom fit, as a fraction of
#: the fitted t-span. Small enough to follow real curvature, wide
#: enough that the second difference doesn't drown in float noise.
_DERIVATIVE_STEP_FRACTION = 1e-3

#: Iteration budget handed to curve_fit. The default (a few
#: hundred) gives up on the stiffer seeds well before they
#: converge; this is generous because a failed solve costs a
#: recompute the user notices, while spare iterations cost
#: nothing on the fits that converge early.
_MAX_FIT_EVALUATIONS = 10000

#: Below this a float difference is numerical noise, not a
#: value: used to catch degenerate spans, flat derivatives and
#: zero residuals without dividing by them.
_NEGLIGIBLE = 1e-12

#: Points sampled when a derivative extremum or the fastest
#: change has to be searched for on a grid rather than read off
#: a parameter — fine enough that the answer lands within a
#: fraction of a capture interval on any series this app sees.
_SEARCH_GRID_POINTS = 512

#: Rate seeds, per unit of the fitted t-span: an exponential
#: decaying over roughly the span, and a sigmoid rising across
#: roughly a quarter of it — the shapes a fluorescence series
#: actually takes, near enough for the optimizer to finish the
#: job.
_EXPONENTIAL_RATE_SEED = -1.0
_SIGMOID_RATE_SEED = 4.0

#: Poor-fit tail trim (opt-in, see fit_series): R² a fit must reach to
#: be accepted, the share of points each retry keeps, and the fewest
#: points worth fitting however poor R² stays.
TRIM_TARGET_R_SQUARED = 0.99
_TRIM_KEEP_FRACTION = 0.9
_TRIM_MIN_POINTS = 10


class FitResult(HasTraits):
    """One fitted model over one ROI's series."""

    method = Str()
    params = Dict()
    equation = Str()
    r_squared = Float()
    #: Vectorized t -> fitted y.
    predict = Any()
    #: Vectorized t -> analytic dy/dt.
    first_derivative = Any()
    #: Vectorized t -> analytic d²y/dt².
    second_derivative = Any()
    #: t of peak |dy/dt| where the model carries it as a parameter
    #: (the sigmoid's inflection); None when it has to be searched for.
    inflection = Any()
    #: The t-range actually solved on — narrower than the series when
    #: the poor-fit tail trim dropped trailing points.
    fitted_start = Float()
    fitted_end = Float()
    #: True when the user gave starting values and they did not
    #: converge, so this fit came from the automatic seeds instead.
    auto_seeded = Bool(False)


def _signed(value):
    """Equation-term join: ' + 3.21' / ' - 3.21' (3 sig-figs)."""
    return f" + {value:.3g}" if value >= 0 else f" - {abs(value):.3g}"


def _poly_equation(coeffs):
    parts = []
    for power, coeff in zip(range(len(coeffs) - 1, -1, -1), coeffs):
        variable = "" if power == 0 else "·t" if power == 1 else f"·t^{power}"
        parts.append(
            f"{coeff:.3g}{variable}" if not parts else f"{_signed(coeff)}{variable}"
        )
    return "y = " + "".join(parts)


def _r_squared(values, fitted):
    residual = values - fitted
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((values - np.mean(values)) ** 2))
    if ss_tot == 0.0:
        return 1.0 if ss_res < _NEGLIGIBLE else 0.0
    return 1.0 - ss_res / ss_tot


def _fit_polynomial(elapsed, values, degree):
    coeffs = np.polyfit(elapsed, values, degree)
    d1_coeffs = np.polyder(coeffs, 1)
    if not len(d1_coeffs):
        d1_coeffs = np.array([0.0])
    d2_coeffs = np.polyder(coeffs, 2)
    if not len(d2_coeffs):  # degree 1: d² is identically zero
        d2_coeffs = np.array([0.0])
    return FitResult(
        params={
            f"c{power}": float(coeff)
            for power, coeff in zip(range(degree, -1, -1), coeffs)
        },
        equation=_poly_equation(coeffs),
        predict=lambda t, coeffs=coeffs: np.polyval(coeffs, t),
        first_derivative=lambda t, d1_coeffs=d1_coeffs: np.polyval(
            d1_coeffs, np.asarray(t, dtype=float)
        ),
        second_derivative=lambda t, d2_coeffs=d2_coeffs: np.polyval(
            d2_coeffs, np.asarray(t, dtype=float)
        ),
    )


def _exponential(t, amplitude, rate, offset):
    return amplitude * np.exp(rate * np.asarray(t, dtype=float)) + offset


def _fit_exponential(elapsed, values):
    t_span = float(elapsed[-1] - elapsed[0]) or 1.0
    offset0 = float(values[-1])
    amplitude0 = float(values[0] - offset0)
    if abs(amplitude0) < _NEGLIGIBLE:
        amplitude0 = float(np.ptp(values)) or 1.0
    params, _ = curve_fit(
        _exponential,
        elapsed,
        values,
        p0=(amplitude0, _EXPONENTIAL_RATE_SEED / t_span, offset0),
        maxfev=_MAX_FIT_EVALUATIONS,
    )
    amplitude, rate, offset = (float(value) for value in params)
    if not all(math.isfinite(value) for value in (amplitude, rate, offset)):
        return None
    return FitResult(
        params={"amplitude": amplitude, "rate": rate, "offset": offset},
        equation=f"y = {amplitude:.3g}·e^({rate:.3g}·t){_signed(offset)}",
        predict=lambda t: _exponential(t, amplitude, rate, offset),
        first_derivative=lambda t: (
            amplitude * rate * np.exp(rate * np.asarray(t, dtype=float))
        ),
        second_derivative=lambda t: (
            amplitude * rate * rate * np.exp(rate * np.asarray(t, dtype=float))
        ),
    )


def _sigmoid(t, amplitude, rate, midpoint, offset):
    return amplitude * expit(rate * (np.asarray(t, dtype=float) - midpoint)) + offset


def _logistic_4p(t, initial, final, midpoint, rate):
    """Four-parameter logistic, the standard melt-curve form:
    y = initial + (final - initial) / (1 + e^(-rate·(t - midpoint))),
    where ``initial``/``final`` are the plateaus approached as t runs
    to -inf/+inf (the classic 4PL lower/upper asymptotes a and k, in
    that order only while the curve rises) and ``midpoint`` is the
    inflection point (Tm). Fitting the plateaus directly keeps both of
    them in the parameter set, where an amplitude-on-offset form hides
    the far one behind a sum."""
    return _sigmoid(t, final - initial, rate, midpoint, initial)


def _fit_sigmoid(elapsed, values):
    t_span = float(elapsed[-1] - elapsed[0]) or 1.0
    initial0 = float(values[0])
    final0 = float(values[-1])
    if abs(final0 - initial0) < _NEGLIGIBLE:
        final0 = initial0 + (float(np.ptp(values)) or 1.0)
    half = (initial0 + final0) / 2.0
    midpoint0 = float(elapsed[int(np.argmin(np.abs(values - half)))])
    params, _ = curve_fit(
        _logistic_4p,
        elapsed,
        values,
        p0=(initial0, final0, midpoint0, _SIGMOID_RATE_SEED / t_span),
        maxfev=_MAX_FIT_EVALUATIONS,
    )
    initial, final, midpoint, rate = (float(value) for value in params)
    if not all(math.isfinite(value) for value in (initial, final, midpoint, rate)):
        return None
    # Canonical rate > 0: since s(-x) == 1 - s(x), swapping the
    # plateaus and negating the rate is the very same curve (a decay
    # then reads as a positive rate with a negative amplitude).
    if rate < 0:
        initial, final, rate = final, initial, -rate

    def sig(t):
        return expit(rate * (np.asarray(t, dtype=float) - midpoint))

    # The plateau separation: what the curve climbs (or falls) through,
    # and the scale factor in both derivatives.
    amplitude = final - initial

    return FitResult(
        # The four the model actually solves for, in the order the
        # template writes them — an amplitude-on-offset pair would hide
        # the far plateau behind a sum, which is the whole reason this
        # fits the 4PL form.
        params={"initial": initial, "final": final, "rate": rate, "midpoint": midpoint},
        inflection=midpoint,
        equation=(
            f"y = {initial:.3g} + ({final:.3g} - {initial:.3g})"
            f"/(1+e^(-{rate:.3g}·(t{_signed(-midpoint)})))"
        ),
        predict=lambda t: _logistic_4p(t, initial, final, midpoint, rate),
        first_derivative=lambda t: amplitude * rate * sig(t) * (1.0 - sig(t)),
        second_derivative=lambda t: (
            amplitude * rate * rate * sig(t) * (1.0 - sig(t)) * (1.0 - 2.0 * sig(t))
        ),
    )


def _numeric_derivatives(predict, step):
    """(first, second) central-difference closures around ``predict``.

    A typed equation has no analytic derivative to hand, and both
    consumers of these — the d²-extrema markers and the fastest-change
    time — only ever sample them on a grid, so differencing satisfies
    the FitResult contract exactly as an analytic form would."""

    def first(t):
        t = np.asarray(t, dtype=float)
        return (predict(t + step) - predict(t - step)) / (2.0 * step)

    def second(t):
        t = np.asarray(t, dtype=float)
        return (predict(t + step) - 2.0 * predict(t) + predict(t - step)) / (
            step * step
        )

    return first, second


def _custom_equation_text(expression, params):
    """The typed equation with each parameter replaced by its fitted
    value — the readable form, in the user's own notation."""
    text = expression.display_text
    for name, value in params.items():
        # Whole words only: a parameter 'a' must not rewrite 'atan'.
        text = re.sub(rf"\b{re.escape(name)}\b", f"{value:.4g}", text)
    return f"y = {text}"


def _custom_seeds(elapsed, values, count):
    """Uniform starting points to try, every parameter at the same
    value. A typed equation says nothing about which of its parameters
    is an amplitude and which is a rate, so instead of guessing per
    name this offers the optimizer one seed per magnitude the data
    suggests and keeps whichever converges best.

    ±1/span earn their place: a rate seeded at 1.0 puts exp(1·t) past
    the float ceiling for any real time axis, and the NEGATIVE one is
    the only seed in this list that recovers a decay — the shape a
    bleaching fluorescence series actually has."""
    span = float(elapsed[-1] - elapsed[0]) or 1.0
    magnitudes = list(_CUSTOM_SEEDS) + [
        float(np.mean(values)),
        float(np.ptp(values)) or 1.0,
        1.0 / span,
        -1.0 / span,
    ]
    return [[magnitude] * count for magnitude in magnitudes]


def _solve_from(expression, elapsed, values, seed):
    """(R², parameters) for one starting point, or None when it does
    not converge to something finite."""
    try:
        solved, _ = curve_fit(
            expression, elapsed, values, p0=seed, maxfev=_MAX_FIT_EVALUATIONS
        )
    except Exception:
        return None
    solved = [float(value) for value in solved]
    if not all(math.isfinite(value) for value in solved):
        return None
    fitted = np.asarray(expression(elapsed, *solved), dtype=float)
    if not np.all(np.isfinite(fitted)):
        return None
    score = _r_squared(values, fitted)
    # A curve so far from the data that the score overflows is not a
    # fit; without this it would out-rank nothing and still be shown.
    if not math.isfinite(score):
        return None
    return score, solved


def user_seed(parameters, initial_guesses):
    """The user's starting point as a p0 list, or None when they have
    not given one for every parameter. All or nothing on purpose: a
    seed is a vector, and filling the gaps with invented numbers would
    be a different starting point than the one they asked for."""
    if not initial_guesses:
        return None
    seed = []
    for name in parameters:
        try:
            value = float(initial_guesses[name])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        seed.append(value)
    return seed


def _fit_custom(elapsed, values, expression, initial_guesses=None):
    """Solve a typed equation. The user's own starting values, when
    they have given a complete set, are tried first and stand if they
    reach any usable fit — a manual seed is an instruction, and quietly
    replacing it with a better-scoring automatic one would make the
    field look like it did nothing. A poor fit from the values asked
    for is honest feedback, and its R² is on display beside it.

    Only a seed that reaches nothing usable at all is abandoned, and
    then the automatic ladder runs and the result says so, rather than
    silently showing a curve the given values never produced."""
    span = float(elapsed[-1] - elapsed[0]) or 1.0
    seed = user_seed(expression.parameters, initial_guesses)
    auto_seeded = False
    best = _solve_from(expression, elapsed, values, seed) if seed else None
    if seed is not None and best is None:
        # Say so rather than silently fitting something else.
        auto_seeded = True
    if best is None:
        for candidate in _custom_seeds(elapsed, values, len(expression.parameters)):
            scored = _solve_from(expression, elapsed, values, candidate)
            if scored is not None and (best is None or scored[0] > best[0]):
                best = scored
    if best is None:
        return None
    params = dict(zip(expression.parameters, best[1]))

    def predict(t, values=best[1]):
        return np.asarray(expression(t, *values), dtype=float)

    first, second = _numeric_derivatives(predict, span * _DERIVATIVE_STEP_FRACTION)
    return FitResult(
        params=params,
        equation=_custom_equation_text(expression, params),
        predict=predict,
        first_derivative=first,
        second_derivative=second,
        auto_seeded=auto_seeded,
    )


def _solve(elapsed, values, method, expression=None, initial_guesses=None):
    """One fit over exactly the points given (already finite-filtered),
    scored and stamped with the domain it used. None when the model
    cannot be solved on them."""
    try:
        # Overflow and invalid values are ordinary events while an
        # optimizer explores — exp() of a rate it is still guessing at
        # runs off the top of a float routinely. What matters is
        # whether the SOLUTION is finite, which is checked below, so
        # the noise is silenced here. Without this, an ambient
        # warnings-as-errors filter turns those transients into
        # exceptions and the best fit is silently thrown away for a
        # worse one that happened not to trip a warning.
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if method == CUSTOM_METHOD:
                result = _fit_custom(elapsed, values, expression, initial_guesses)
            elif method == "exponential":
                result = _fit_exponential(elapsed, values)
            elif method == "sigmoid":
                result = _fit_sigmoid(elapsed, values)
            else:
                result = _fit_polynomial(
                    elapsed, values, {"linear": 1, "poly2": 2, "poly3": 3}[method]
                )
    except Exception:
        return None
    if result is None:
        return None
    result.method = method
    result.r_squared = _r_squared(values, result.predict(elapsed))
    result.fitted_start = float(elapsed[0])
    result.fitted_end = float(elapsed[-1])
    return result


def fit_series(
    elapsed, values, method, trim_tail=False, expression="", initial_guesses=None
):
    """Fit one series. None when fitting is off, too few finite points
    remain after NaN filtering, or the optimizer fails — callers render
    that as "fit failed", never a traceback. ``expression`` is the typed
    equation, used when ``method`` is CUSTOM_METHOD and ignored
    otherwise; one that does not parse fits nothing.
    ``initial_guesses`` is {parameter: starting value} for that
    equation — see _fit_custom for how a partial or failing one is
    treated.

    ``trim_tail`` retries a fit that misses TRIM_TARGET_R_SQUARED on
    successively shorter leading slices, the qPCR trick for a tail the
    model does not describe (a bleaching plateau drags a sigmoid's
    inflection early). The first slice reaching the target wins; when
    none does, the full-series fit stands rather than paying data for
    nothing. Read ``fitted_start``/``fitted_end`` for what was used —
    everything past it is extrapolation."""
    parsed = None
    if method == CUSTOM_METHOD:
        try:
            parsed = parse_expression(expression)
        except FitExpressionError:
            return None
        # A curve through N parameters needs more than N points to say
        # anything; one point per parameter merely interpolates.
        minimum = len(parsed.parameters) + 1
    elif method in _MIN_POINTS:
        minimum = _MIN_POINTS[method]
    else:
        return None
    elapsed = np.asarray(elapsed, dtype=float)
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(elapsed) & np.isfinite(values)
    elapsed, values = elapsed[finite], values[finite]
    if len(elapsed) < minimum:
        return None
    result = _solve(elapsed, values, method, parsed, initial_guesses)
    if result is None or not trim_tail or result.r_squared >= TRIM_TARGET_R_SQUARED:
        return result
    floor = max(minimum, _TRIM_MIN_POINTS)
    kept = len(elapsed)
    while kept > floor:
        # min() with kept - 1 keeps short series shrinking at all.
        kept = min(kept - 1, int(kept * _TRIM_KEEP_FRACTION))
        if kept < floor:
            break
        trimmed = _solve(elapsed[:kept], values[:kept], method, parsed, initial_guesses)
        if trimmed is not None and trimmed.r_squared >= TRIM_TARGET_R_SQUARED:
            return trimmed
    return result


def trimmed_note(fit, t_end):
    """' (fit to t ≤ 150 s)' when the trim dropped the tail, '' when
    the whole series was used — so every readout of an equation says
    what it was solved on."""
    if fit.fitted_end >= float(t_end):
        return ""
    return f" (fit to t ≤ {fit.fitted_end:.4g} s)"


def second_derivative_extrema(fit, t_start, t_end):
    """{"max": (t, y_on_curve), "min": (t, y_on_curve)} over
    [t_start, t_end] — the y is the FITTED CURVE's value there, so the
    marker sits on the curve. {} when d² is flat (linear/quadratic):
    no meaningful extremum, draw nothing rather than mislead."""
    grid = np.linspace(float(t_start), float(t_end), _SEARCH_GRID_POINTS)
    d2 = np.asarray(fit.second_derivative(grid), dtype=float)
    if d2.shape != grid.shape:  # scalar-returning closure
        d2 = np.full_like(grid, float(d2))
    if not np.all(np.isfinite(d2)):
        return {}
    if float(np.ptp(d2)) <= _NEGLIGIBLE * max(1.0, float(np.max(np.abs(d2)))):
        return {}
    t_max = float(grid[int(np.argmax(d2))])
    t_min = float(grid[int(np.argmin(d2))])
    return {
        "max": (t_max, float(fit.predict(t_max))),
        "min": (t_min, float(fit.predict(t_min))),
    }


def fastest_change_time(fit, t_start, t_end):
    """The t in [t_start, t_end] where |dy/dt| of the fitted curve
    peaks. A sigmoid answers from its own fitted inflection, so a
    trimmed fit still reports the real crossing instead of the edge of
    the slice it was solved on; other models are searched on a grid.
    None when the speed is flat (linear fits): no meaningful "fastest"
    moment exists, so callers draw nothing rather than an arbitrary
    bar."""
    grid = np.linspace(float(t_start), float(t_end), _SEARCH_GRID_POINTS)
    speed = np.abs(np.asarray(fit.first_derivative(grid), dtype=float))
    if speed.shape != grid.shape:  # scalar-returning closure
        speed = np.full_like(grid, float(speed))
    if not np.all(np.isfinite(speed)):
        return None
    if float(np.ptp(speed)) <= _NEGLIGIBLE * max(1.0, float(np.max(speed))):
        return None
    # Outside the window the parameter is no answer to "when, in what
    # we plotted?" — there the rate is monotonic and the edge is.
    if fit.inflection is not None and float(t_start) <= fit.inflection <= float(t_end):
        return float(fit.inflection)
    return float(grid[int(np.argmax(speed))])

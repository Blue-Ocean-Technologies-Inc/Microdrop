# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Saved fit equations: the built-ins plus whatever the user has added,
and the JSON they are kept in. App-wide rather than per-experiment — an
equation that had to be re-typed for every experiment would not be a
preset. Qt-free."""

# Standard library imports.
import json

# Local imports.
from .curve_fit import CUSTOM_METHOD, FIT_LABELS, FIT_METHODS, FIT_TEMPLATES
from .fit_expression import FitExpressionError, parse_expression

#: Prefix marking a method key as one of the user's saved equations,
#: keeping them in a namespace the built-ins can never collide with.
PRESET_PREFIX = "preset:"


def load_presets(text):
    """[(name, expression), ...] from the stored JSON. Anything
    unreadable, or any entry that no longer parses, is dropped — a
    corrupt preferences string must not stop the plugin loading."""
    try:
        payload = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    presets = []
    for entry in payload if isinstance(payload, list) else []:
        try:
            name = str(entry["name"]).strip()
            expression = str(entry["expression"]).strip()
        except (KeyError, TypeError):
            continue
        if name and expression and is_parsable(expression):
            presets.append((name, expression))
    return presets


def save_presets(presets):
    """The JSON for ``[(name, expression), ...]``."""
    return json.dumps(
        [{"name": name, "expression": expression} for name, expression in presets]
    )


def is_parsable(expression):
    try:
        parse_expression(expression)
    except FitExpressionError:
        return False
    return True


def add_preset(presets, name, expression):
    """``presets`` with ``name`` set to ``expression`` — replacing any
    preset of that name rather than admitting two, since the name is
    what the dropdown offers."""
    kept = [(existing, text) for existing, text in presets if existing != name]
    return kept + [(name, expression)]


def method_keys(presets):
    """Every selectable fit method: the built-ins, then the saved
    equations. CUSTOM_METHOD is not among them — it is what the model
    holds while an equation is typed but unsaved, and it appears in the
    dropdown only when that is the case."""
    return list(FIT_METHODS) + [PRESET_PREFIX + name for name, _ in presets]


def choices_for(presets, current=""):
    """The dropdown's keys. ``current`` is appended when it is not one
    of them — that is CUSTOM_METHOD while an equation is typed but
    unsaved, and also a stale "preset:<deleted>" from an experiment
    saved before the preset was removed, which must stay selectable
    rather than snapping the dropdown onto some other fit."""
    keys = method_keys(presets)
    if current and current not in keys:
        keys.append(current)
    return keys


def method_label(key, presets):
    """The dropdown text for one method key."""
    if key.startswith(PRESET_PREFIX):
        return key[len(PRESET_PREFIX) :]
    return FIT_LABELS.get(key, key)


def expression_for(key, presets, custom_expression=""):
    """The equation text a method fits: a preset's own, a built-in's
    display template, or — for CUSTOM_METHOD — whatever is typed.
    '' for "no fit", which has no equation."""
    if key == CUSTOM_METHOD:
        return custom_expression
    if key.startswith(PRESET_PREFIX):
        wanted = key[len(PRESET_PREFIX) :]
        for name, expression in presets:
            if name == wanted:
                return expression
        return ""
    return FIT_TEMPLATES.get(key, "")


def method_for_expression(text, presets):
    """The method key that already fits ``text``, or '' when nothing
    does — which is what enables the add-to-presets button. Whitespace
    is ignored so a stray space is not a new equation."""

    def squashed(value):
        return "".join(value.split())

    target = squashed(text)
    if not target:
        return ""
    for name, expression in presets:
        if squashed(expression) == target:
            return PRESET_PREFIX + name
    for key, template in FIT_TEMPLATES.items():
        if squashed(template) == target:
            return key
    return ""


def solving_method(key):
    """How a method key is actually solved: a saved preset is fitted as
    a custom equation, the built-ins by their own implementations."""
    return CUSTOM_METHOD if key.startswith(PRESET_PREFIX) else key


def fit_arguments(figure, presets):
    """(method, expression) for fit_series from a figure's settings —
    the one place that turns a stored method key into a solve, so every
    caller fits the same thing."""
    key = figure.fit_method
    return (solving_method(key), expression_for(key, presets, figure.custom_expression))

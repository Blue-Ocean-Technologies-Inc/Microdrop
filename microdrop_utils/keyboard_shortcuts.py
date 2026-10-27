# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Key parsing and lookups over a plugin's keyboard shortcut table.

A table is a sequence of ``(key sequence, action, description, group)``
rows with unique sequences; a second key for one action gets an action of
its own named ``<action>_alt`` or ``<action>_equal``.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui

Qt = QtCore.Qt

# Suffixes of the second-key rows that run their primary action.
ALTERNATE_ACTION_SUFFIXES = ("_alt", "_equal")


def primary_action(action):
    """Return the action an alternate-key row stands for."""
    for suffix in ALTERNATE_ACTION_SUFFIXES:
        if action.endswith(suffix):
            return action.removesuffix(suffix)

    return action


def native_key_text(sequence):
    """Return ``sequence`` as the platform spells it, as "Ctrl+Z" or "⌘Z"."""
    return QtGui.QKeySequence(sequence).toString(
        QtGui.QKeySequence.SequenceFormat.NativeText
    )


def key_sequence_of(event):
    """Return the event's keys, ignoring the keypad flag.

    Numpad keys, and on macOS the arrows, carry KeypadModifier; the table
    names the key alone.
    """
    combination = event.keyCombination()
    modifiers = combination.keyboardModifiers() & ~Qt.KeyboardModifier.KeypadModifier

    return QtGui.QKeySequence(QtCore.QKeyCombination(modifiers, combination.key()))


def actions_by_sequence(table):
    """Return ``{QKeySequence: action}`` for looking up a key event's row."""
    return {QtGui.QKeySequence(sequence): action for sequence, action, _, _ in table}


def shortcut_label(table, action):
    """Return the native key text of the first row bound to ``action``."""
    return next(
        (
            native_key_text(sequence)
            for sequence, row_action, _, _ in table
            if row_action == action
        ),
        "",
    )


def tooltip_with_shortcut(table, tooltip, action):
    """Append the key bound to ``action``, as "Draw (D)"."""
    label = shortcut_label(table, action)

    if not label:
        return tooltip

    return f"{tooltip} ({label})"


def cheat_sheet_rows(table, groups):
    """Return ``[(group, [(keys, description)])]`` in ``groups`` order.

    An alternate-key row is folded into its primary row's keys, as
    "F1 / Ctrl+/".
    """
    keys_by_action = {}
    rows_by_group = {group: [] for group in groups}

    for sequence, action, description, group in table:
        primary = primary_action(action)

        if primary in keys_by_action:
            keys_by_action[primary].append(native_key_text(sequence))
            continue

        keys_by_action[primary] = [native_key_text(sequence)]
        rows_by_group[group].append((primary, description))

    return [
        (
            group,
            [(" / ".join(keys_by_action[action]), text) for action, text in rows],
        )
        for group, rows in rows_by_group.items()
    ]

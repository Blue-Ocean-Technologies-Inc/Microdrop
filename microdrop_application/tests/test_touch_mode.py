# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for Touch mode: the number pad's entry logic, its placement beside
the field, and the touch stylesheet block."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtCore import QPoint, QRect, QSize

# Microdrop package imports.
from microdrop_application.preferences import MicrodropPreferences
from microdrop_application.touch_mode.consts import UNBOUNDED_TEXT
from microdrop_application.touch_mode.number_entry import NumberEntry, format_number
from microdrop_application.touch_mode.number_pad import place_beside

# Microdrop style imports.
from microdrop_style.helpers import (
    DOCK_SEPARATOR_STYLE_START_MARKER,
    TOUCH_STYLE_START_MARKER,
    apply_dock_separator_style,
    apply_touch_style,
)

# Microdrop utils imports.
from microdrop_utils.system_config import is_rpi
from microdrop_utils.traitsui_qt_helpers import DOUBLE_SPINBOX_UNBOUNDED_MAX

SCREEN = QRect(0, 0, 1280, 800)
PAD_SIZE = QSize(300, 420)
GAP = 6


def make_entry(value, minimum=0.0, maximum=100.0, decimals=0):
    entry = NumberEntry(minimum=minimum, maximum=maximum, decimals=decimals)
    entry.start(value)

    return entry


def type_keys(entry, keys):
    actions = {
        ".": entry.type_point,
        "±": entry.toggle_sign,
        "⌫": entry.backspace,
        "C": entry.clear,
    }

    for key in keys:
        if key in actions:
            actions[key]()
        else:
            entry.type_digit(key)


def test_touch_mode_preference_defaults_to_the_portable_rig():
    preferences = MicrodropPreferences(preferences=Preferences())

    assert preferences.touch_mode == is_rpi()


@pytest.mark.parametrize(
    "value, decimals, expected",
    [
        (200.0, 0, "200"),
        (0.5, 2, "0.5"),
        (1.25, 2, "1.25"),
        (-0.0, 1, "0"),
        (DOUBLE_SPINBOX_UNBOUNDED_MAX, 2, UNBOUNDED_TEXT),
        (-DOUBLE_SPINBOX_UNBOUNDED_MAX, 2, f"-{UNBOUNDED_TEXT}"),
    ],
)
def test_format_number(value, decimals, expected):
    assert format_number(value, decimals) == expected


def test_first_digit_replaces_the_selected_initial_value():
    entry = make_entry(42)

    assert entry.text == "42"
    assert entry.replace_pending

    type_keys(entry, "7")

    assert entry.text == "7"
    assert not entry.replace_pending

    type_keys(entry, "5")

    assert entry.value == 75


@pytest.mark.parametrize(
    "keys, expected_text",
    [
        ("⌫", ""),
        ("12⌫", "1"),
        ("12C", ""),
        ("007", "7"),
        ("0.05", "0.05"),
        (".5", "0.5"),
        ("1.2.3", "1.23"),
        ("1.234", "1.23"),
    ],
)
def test_keys_edit_the_text(keys, expected_text):
    entry = make_entry(42, decimals=2)

    type_keys(entry, keys)

    assert entry.text == expected_text


def test_integer_entry_has_no_point():
    entry = make_entry(42)

    assert not entry.allows_point

    type_keys(entry, "1.5")

    assert entry.text == "15"


def test_sign_needs_a_negative_minimum():
    entry = make_entry(5, minimum=0)
    type_keys(entry, "±")

    assert not entry.allows_negative
    assert entry.text == "5"

    entry = make_entry(5, minimum=-50, maximum=50)
    type_keys(entry, "±")

    assert entry.text == "-5"
    assert entry.value == -5

    type_keys(entry, "3±")

    assert entry.text == "53"


@pytest.mark.parametrize(
    "keys, in_range, out_of_range",
    [
        ("50", True, False),
        ("200", False, True),
        ("C", False, False),
        ("±", False, False),
    ],
)
def test_range_validation(keys, in_range, out_of_range):
    entry = make_entry(100, minimum=-100, maximum=150)
    type_keys(entry, "C")
    type_keys(entry, keys)

    assert entry.in_range == in_range
    assert entry.out_of_range == out_of_range


def test_range_text_carries_the_affixes():
    entry = make_entry(100, minimum=30, maximum=200)

    assert entry.range_text(suffix=" V") == "30 – 200 V"


def test_pad_goes_below_the_field_when_it_fits():
    field = QRect(100, 100, 200, 44)

    position = place_beside(PAD_SIZE, field, SCREEN, GAP)

    assert position == QPoint(100, field.bottom() + 1 + GAP)


def test_pad_flips_away_from_the_screen_edges():
    field = QRect(1100, 700, 160, 44)

    pad = QRect(place_beside(PAD_SIZE, field, SCREEN, GAP), PAD_SIZE)

    assert SCREEN.contains(pad)
    assert not pad.intersects(field)


def test_pad_stays_on_screen_when_nothing_fits_beside_the_field():
    field = QRect(0, 0, 1280, 800)

    pad = QRect(place_beside(PAD_SIZE, field, SCREEN, GAP), PAD_SIZE)

    assert SCREEN.contains(pad)


def test_touch_style_block_is_added_once_and_removed(qapp):
    previous_style_sheet = qapp.styleSheet()
    other_rules = "QLabel { color: red; }\n"
    qapp.setStyleSheet(other_rules)

    try:
        apply_dock_separator_style("#123456")
        apply_touch_style(True)
        apply_touch_style(True)

        style_sheet = qapp.styleSheet()

        assert style_sheet.count(TOUCH_STYLE_START_MARKER) == 1
        assert style_sheet.count(DOCK_SEPARATOR_STYLE_START_MARKER) == 1
        assert "QAbstractSpinBox::up-button" in style_sheet

        apply_touch_style(False)

        assert TOUCH_STYLE_START_MARKER not in qapp.styleSheet()
        assert DOCK_SEPARATOR_STYLE_START_MARKER in qapp.styleSheet()

        apply_dock_separator_style(None)

        assert qapp.styleSheet() == other_rules
    finally:
        qapp.setStyleSheet(previous_style_sheet)

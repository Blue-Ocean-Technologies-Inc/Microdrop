# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the dock-separator colour preference and its stylesheet block."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtGui import QColor

# Microdrop package imports.
from microdrop_application.consts import (
    COLOR_SCHEME_DARK,
    COLOR_SCHEME_FOLLOW_SYSTEM,
    COLOR_SCHEME_LIGHT,
    DOCK_SEPARATOR_COLOR_CUSTOM,
)
from microdrop_application.helpers import resolve_dock_separator_style
from microdrop_application.preferences import MicrodropPreferences

# Microdrop style imports.
from microdrop_style.colors import ACCENT_COLOR, GREY
from microdrop_style.dock_separator_style import (
    DOCK_SEPARATOR_THEME_COLORS,
    SEPARATOR_THICKNESS,
    get_dock_separator_style,
)
from microdrop_style.helpers import (
    DOCK_SEPARATOR_STYLE_START_MARKER,
    apply_dock_separator_style,
)

CUSTOM_COLOR = "#123456"


def test_dock_separator_preferences_default():
    preferences = MicrodropPreferences(preferences=Preferences())

    assert preferences.dock_separator_color_mode == COLOR_SCHEME_FOLLOW_SYSTEM
    assert preferences.dock_separator_color == QColor(GREY["light"])


def test_dock_separator_style_without_thickness_keeps_native_extent():
    style = get_dock_separator_style(CUSTOM_COLOR)

    assert f"background-color: {CUSTOM_COLOR};" in style
    assert f"background-color: {ACCENT_COLOR};" in style
    assert "width" not in style
    assert "height" not in style


def test_dock_separator_style_with_thickness_sizes_both_orientations():
    style = get_dock_separator_style(CUSTOM_COLOR, SEPARATOR_THICKNESS)

    assert f"width: {SEPARATOR_THICKNESS}px;" in style
    assert f"height: {SEPARATOR_THICKNESS}px;" in style


@pytest.mark.parametrize(
    "color_mode, dark_mode, expected_color",
    [
        (COLOR_SCHEME_FOLLOW_SYSTEM, False, DOCK_SEPARATOR_THEME_COLORS["light"]),
        (COLOR_SCHEME_FOLLOW_SYSTEM, True, DOCK_SEPARATOR_THEME_COLORS["dark"]),
        (COLOR_SCHEME_LIGHT, True, DOCK_SEPARATOR_THEME_COLORS["light"]),
        (COLOR_SCHEME_DARK, False, DOCK_SEPARATOR_THEME_COLORS["dark"]),
        (DOCK_SEPARATOR_COLOR_CUSTOM, True, CUSTOM_COLOR),
    ],
)
@pytest.mark.parametrize(
    "rpi, expected_thickness", [(True, SEPARATOR_THICKNESS), (False, None)]
)
def test_resolve_dock_separator_style(
    color_mode, dark_mode, expected_color, rpi, expected_thickness
):
    resolved = resolve_dock_separator_style(color_mode, CUSTOM_COLOR, dark_mode, rpi)

    assert resolved == (expected_color, expected_thickness)


def test_apply_dock_separator_style_replaces_block_and_removes_it(qapp):
    previous_style_sheet = qapp.styleSheet()
    other_rules = "QLabel { color: red; }\n"
    qapp.setStyleSheet(other_rules)

    try:
        apply_dock_separator_style(DOCK_SEPARATOR_THEME_COLORS["light"])
        apply_dock_separator_style(CUSTOM_COLOR, SEPARATOR_THICKNESS)

        style_sheet = qapp.styleSheet()

        assert style_sheet.count(DOCK_SEPARATOR_STYLE_START_MARKER) == 1
        assert CUSTOM_COLOR in style_sheet
        assert DOCK_SEPARATOR_THEME_COLORS["light"] not in style_sheet
        assert style_sheet.startswith(other_rules)

        apply_dock_separator_style(None)

        assert qapp.styleSheet() == other_rules
    finally:
        qapp.setStyleSheet(previous_style_sheet)

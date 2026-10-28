# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the app-wide colour-scheme override preference."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QPalette
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from microdrop_application.consts import (
    COLOR_SCHEME_DARK,
    COLOR_SCHEME_FOLLOW_SYSTEM,
    COLOR_SCHEME_LIGHT,
)
from microdrop_application.preferences import MicrodropPreferences

# Microdrop style imports.
from microdrop_style.helpers import apply_color_scheme, is_dark_mode


def _platform_ignores_color_scheme_requests():
    """Platform themes without colour-scheme support report Unknown."""
    return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Unknown


def _window_color():
    return QApplication.palette().color(QPalette.ColorRole.Window)


def test_color_scheme_defaults_to_follow_system():
    assert MicrodropPreferences(preferences=Preferences()).color_scheme == (
        COLOR_SCHEME_FOLLOW_SYSTEM
    )


def test_color_scheme_round_trips_through_preferences_node():
    node = Preferences()
    listening_helper = MicrodropPreferences(preferences=node)
    writing_helper = MicrodropPreferences(preferences=node)

    # Dark first, so writing the follow_system default is a real change.
    for color_scheme in (
        COLOR_SCHEME_DARK,
        COLOR_SCHEME_LIGHT,
        COLOR_SCHEME_FOLLOW_SYSTEM,
    ):
        writing_helper.color_scheme = color_scheme

        assert node.get("microdrop.app.color_scheme") == color_scheme
        assert MicrodropPreferences(preferences=node).color_scheme == color_scheme

        # A helper already bound to the node (the application's) follows it.
        assert listening_helper.color_scheme == color_scheme


def test_apply_color_scheme_fallback_when_platform_ignores_requests(qapp):
    if not _platform_ignores_color_scheme_requests():
        pytest.skip(f"{qapp.platformName()} platform honours colour-scheme requests")

    style_hints = QApplication.styleHints()
    startup_window_color = _window_color()
    received = []
    style_hints.colorSchemeChanged.connect(received.append)

    try:
        apply_color_scheme(COLOR_SCHEME_DARK)

        assert is_dark_mode()
        assert received[-1] == Qt.ColorScheme.Dark
        assert _window_color().lightness() < 128

        apply_color_scheme(COLOR_SCHEME_LIGHT)

        assert not is_dark_mode()
        assert received[-1] == Qt.ColorScheme.Light
        assert _window_color() == startup_window_color

        apply_color_scheme(COLOR_SCHEME_DARK)
        apply_color_scheme(COLOR_SCHEME_FOLLOW_SYSTEM)

        assert not is_dark_mode()
        assert received[-1] == style_hints.colorScheme()
        assert _window_color() == startup_window_color
    finally:
        style_hints.colorSchemeChanged.disconnect(received.append)
        apply_color_scheme(COLOR_SCHEME_FOLLOW_SYSTEM)


def test_apply_color_scheme_flips_dark_mode_and_restores_system(qapp):
    if _platform_ignores_color_scheme_requests():
        pytest.skip(f"{qapp.platformName()} platform ignores colour-scheme requests")

    style_hints = QApplication.styleHints()
    system_scheme = style_hints.colorScheme()

    apply_color_scheme(COLOR_SCHEME_DARK)

    assert style_hints.colorScheme() == Qt.ColorScheme.Dark
    assert is_dark_mode()

    apply_color_scheme(COLOR_SCHEME_LIGHT)

    assert style_hints.colorScheme() == Qt.ColorScheme.Light
    assert not is_dark_mode()

    apply_color_scheme(COLOR_SCHEME_FOLLOW_SYSTEM)

    assert style_hints.colorScheme() == system_scheme
    assert is_dark_mode() == (system_scheme == Qt.ColorScheme.Dark)

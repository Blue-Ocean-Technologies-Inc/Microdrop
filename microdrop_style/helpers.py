# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont, QIcon
from pyface.qt.QtWidgets import QApplication

# Local imports.
from .button_styles import get_button_style, get_tooltip_style
from .combo_box_style import get_combobox_style
from .font_paths import load_font_and_get_family
from .general_style import get_general_style
from .label_style import get_label_style
from .message_box_style import get_message_box_style
from .palettes import dark_palette

QT_THEME_NAMES = {Qt.ColorScheme.Dark: "dark", Qt.ColorScheme.Light: "light"}

# The scheme forced by apply_color_scheme (None follows the OS), and the app
# palette from before the first override, restored when following the OS.
_requested_color_scheme = None
_startup_palette = None


def is_dark_mode():
    if _requested_color_scheme is not None:
        return _requested_color_scheme == Qt.ColorScheme.Dark

    return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def apply_color_scheme(color_scheme):
    """Force the app to a QT_THEME_NAMES scheme, or follow the OS for any other.

    Qt emits ``colorSchemeChanged`` when the effective scheme changes, so every
    widget already listening for OS theme switches re-styles itself.
    """
    global _requested_color_scheme, _startup_palette

    style_hints = QApplication.styleHints()
    qt_color_schemes = {name: scheme for scheme, name in QT_THEME_NAMES.items()}

    if _startup_palette is None:
        _startup_palette = QApplication.palette()

    _requested_color_scheme = qt_color_schemes.get(color_scheme)

    if _requested_color_scheme is None:
        style_hints.unsetColorScheme()
    else:
        style_hints.setColorScheme(_requested_color_scheme)

    current_color_scheme = style_hints.colorScheme()

    if _requested_color_scheme is None:
        platform_applied_it = current_color_scheme != Qt.ColorScheme.Unknown
    else:
        platform_applied_it = current_color_scheme == _requested_color_scheme

    if platform_applied_it:
        return

    # Platform themes without colour-scheme support (offscreen, and xcb on
    # the Pi with or without qt5ct/gtk3) ignore the request: no palette
    # change, no signal. Swap the palette and announce the scheme ourselves;
    # is_dark_mode() reports the override. The startup palette is light there.
    if _requested_color_scheme == Qt.ColorScheme.Dark:
        QApplication.setPalette(dark_palette())
    else:
        QApplication.setPalette(_startup_palette)

    style_hints.colorSchemeChanged.emit(_requested_color_scheme or current_color_scheme)


def style_app(app_instance: "QApplication"):
    # Load the icon fonts (Material Symbols + Pictogrammers' Material
    # Design Icons — the latter has no ligatures, use \U000Fxxxx codepoints)
    load_font_and_get_family("material_symbols")
    load_font_and_get_family("material_design_icons")
    # load inter font and set with some size
    LABEL_FONT_FAMILY = load_font_and_get_family("inter")

    app_instance.setFont(QFont(LABEL_FONT_FAMILY, 11))
    QIcon.setThemeName("Material Symbols Outlined")


def get_complete_stylesheet(theme="light", button_type="default"):
    """
    Combines all modular styles into one cohesive sheet.
    """
    general = get_general_style(theme)
    labels = get_label_style(theme)
    combos = get_combobox_style(theme)
    buttons = get_button_style(theme, button_type)
    tooltips = get_tooltip_style(theme)
    message_box = get_message_box_style(theme)

    # Order matters slightly: General generic rules first, specific widgets last.
    return f"{general}\n{labels}\n{combos}\n{buttons}\n{tooltips}{message_box}"

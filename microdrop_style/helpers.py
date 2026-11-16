# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import re

# Enthought library imports.
from pyface.qt.QtCore import QCoreApplication, QEvent, Qt, QTimer
from pyface.qt.QtGui import QColor, QFont, QIcon, QPalette
from pyface.qt.QtWidgets import QApplication

# Local imports.
from .button_styles import get_button_style, get_tooltip_style
from .combo_box_style import get_combobox_style
from .dock_separator_style import get_dock_separator_style
from .font_paths import load_font_and_get_family
from .general_style import get_general_style
from .label_style import get_label_style
from .message_box_style import get_message_box_style
from .palettes import dark_palette
from .touch_style import get_touch_style

QT_THEME_NAMES = {Qt.ColorScheme.Dark: "dark", Qt.ColorScheme.Light: "light"}

# Window lightness below which a palette counts as dark. Platform themes can
# report a scheme their palette does not carry, so the palette is checked too.
DARK_PALETTE_LIGHTNESS_THRESHOLD = 128

# The scheme forced by apply_color_scheme (None follows the OS), the app
# palette from before the first override, restored when following the OS, and
# whether colour-scheme changes already trigger refresh_widget_palettes.
_requested_color_scheme = None
_startup_palette = None
_palette_refresh_installed = False

# Brackets for the dock-separator rules inside the application stylesheet, so
# they are replaced in place and other contributors' rules survive.
DOCK_SEPARATOR_STYLE_START_MARKER = "/* dock-separator */"
DOCK_SEPARATOR_STYLE_END_MARKER = "/* /dock-separator */"

# Brackets for the touch-mode rules inside the application stylesheet.
TOUCH_STYLE_START_MARKER = "/* touch-mode */"
TOUCH_STYLE_END_MARKER = "/* /touch-mode */"

# TraitsUI's field-error colours and the Base HSV value below which it picks
# the dark one; they mirror the literals in traitsui.qt.constants.
TRAITSUI_DARK_BASE_VALUE_THRESHOLD = 0x80
TRAITSUI_DARK_ERROR_COLOR = "#cf6679"
TRAITSUI_LIGHT_ERROR_COLOR = "#ffc0c0"


def is_dark_mode():
    if _requested_color_scheme is not None:
        return _requested_color_scheme == Qt.ColorScheme.Dark

    return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def refresh_widget_palettes():
    """Tell every non-window widget to re-resolve its palette from the app's.

    Qt only tells top-level windows about a global palette change, and an app
    stylesheet turns off parent-to-child palette inheritance.
    """
    for widget in QApplication.allWidgets():
        if not widget.isWindow():
            QCoreApplication.sendEvent(
                widget, QEvent(QEvent.Type.ApplicationPaletteChange)
            )


def sync_traitsui_field_colors(palette):
    """Re-derive TraitsUI's field colours from ``palette`` and repaint its fields.

    ``traitsui.qt.constants`` snapshots the application palette at import, and
    every text editor paints its field's Base from that snapshot. The editor
    modules hold the colour objects themselves, so they are updated in place:
    rebinding the module names would not reach them. Fields already painted
    carry the old colour as an explicit widget palette, which no application
    palette change overrides, so they are repainted too.
    """
    # TraitsUI snapshots these at import, before our palette override; imported
    # here because importing it takes that snapshot and needs a QApplication.
    from traitsui.qt import constants

    base = palette.color(QPalette.ColorRole.Base)

    if base.value() < TRAITSUI_DARK_BASE_VALUE_THRESHOLD:
        error_color = QColor(TRAITSUI_DARK_ERROR_COLOR)
    else:
        error_color = QColor(TRAITSUI_LIGHT_ERROR_COLOR)

    color_updates = [
        (constants.OKColor, base),
        (constants.DropColor, base),
        (constants.ErrorColor, error_color),
        (constants.ReadonlyColor, palette.color(QPalette.ColorRole.Window)),
    ]
    updated_colors = {color.rgba(): color for color, _new_color in color_updates}

    for color, new_color in color_updates:
        color.setRgba(new_color.rgba())

    for widget in QApplication.allWidgets():
        ok_color = getattr(widget, "_ok_color", None)

        if ok_color is not None and ok_color.rgba() in updated_colors:
            widget._ok_color = QColor(updated_colors[ok_color.rgba()])

        if not widget.testAttribute(Qt.WidgetAttribute.WA_SetPalette):
            continue

        widget_palette = QPalette(widget.palette())
        old_base = widget_palette.color(QPalette.ColorRole.Base).rgba()

        if old_base in updated_colors:
            widget_palette.setColor(QPalette.ColorRole.Base, updated_colors[old_base])
            widget.setPalette(widget_palette)


def apply_color_scheme(color_scheme):
    """Force the app to a QT_THEME_NAMES scheme, or follow the OS for any other.

    Qt emits ``colorSchemeChanged`` when the effective scheme changes, so every
    widget already listening for OS theme switches re-styles itself.
    """
    global _requested_color_scheme, _startup_palette, _palette_refresh_installed

    style_hints = QApplication.styleHints()
    qt_color_schemes = {name: scheme for scheme, name in QT_THEME_NAMES.items()}

    if not _palette_refresh_installed:
        # Deferred: Qt may emit before the platform palette lands. The
        # fallback's manual emit below triggers a second, harmless refresh.
        style_hints.colorSchemeChanged.connect(
            lambda _color_scheme: QTimer.singleShot(0, refresh_widget_palettes)
        )
        _palette_refresh_installed = True

    if _startup_palette is None:
        _startup_palette = QApplication.palette()

    _requested_color_scheme = qt_color_schemes.get(color_scheme)

    if _requested_color_scheme is None:
        style_hints.unsetColorScheme()
    else:
        style_hints.setColorScheme(_requested_color_scheme)

    current_color_scheme = style_hints.colorScheme()
    color_scheme_in_force = _requested_color_scheme or current_color_scheme

    if _requested_color_scheme is None:
        platform_applied_it = current_color_scheme != Qt.ColorScheme.Unknown
    else:
        platform_applied_it = current_color_scheme == _requested_color_scheme

    palette_is_dark = (
        QApplication.palette().window().color().lightness()
        < DARK_PALETTE_LIGHTNESS_THRESHOLD
    )
    palette_matches_it = palette_is_dark == (
        color_scheme_in_force == Qt.ColorScheme.Dark
    )

    if platform_applied_it and palette_matches_it:
        sync_traitsui_field_colors(QApplication.palette())

        return

    # Platform themes without colour-scheme support (offscreen, and xcb on
    # the Pi with or without qt5ct/gtk3) ignore the request: no palette
    # change, no signal. The Pi's gnome theme instead reports the scheme but
    # keeps its light palette. Swap the palette and announce the scheme
    # ourselves; is_dark_mode() reports the override. The startup palette is
    # light there.
    if color_scheme_in_force == Qt.ColorScheme.Dark:
        QApplication.setPalette(dark_palette())
    else:
        QApplication.setPalette(_startup_palette)

    sync_traitsui_field_colors(QApplication.palette())
    refresh_widget_palettes()

    style_hints.colorSchemeChanged.emit(color_scheme_in_force)


def apply_style_sheet_block(start_marker, end_marker, rules):
    """Write ``rules`` into the application stylesheet between the markers.

    The previously applied block is replaced, so repeated calls never
    accumulate rules, and rules outside the markers survive. ``rules`` of
    None removes the block.
    """
    app = QApplication.instance()
    current_style_sheet = app.styleSheet()
    block = ""

    if rules is not None:
        block = f"{start_marker}{rules}{end_marker}\n"

    block_pattern = re.compile(
        f"{re.escape(start_marker)}.*?{re.escape(end_marker)}\n?", re.DOTALL
    )
    style_sheet, replaced = block_pattern.subn(
        lambda _match: block, current_style_sheet, count=1
    )

    if not replaced:
        style_sheet = current_style_sheet + block

    # Re-setting an unchanged sheet would still re-polish every widget.
    if style_sheet != current_style_sheet:
        app.setStyleSheet(style_sheet)


def apply_dock_separator_style(color, thickness=None):
    """Write the dock-separator rules into the application stylesheet.

    A ``color`` of None removes them, restoring the native separators.
    """
    rules = None

    if color is not None:
        rules = get_dock_separator_style(color, thickness)

    apply_style_sheet_block(
        DOCK_SEPARATOR_STYLE_START_MARKER, DOCK_SEPARATOR_STYLE_END_MARKER, rules
    )


def apply_touch_style(enabled):
    """Write the touch-mode rules, coloured from the current application
    palette, into the application stylesheet, or remove them.
    """
    rules = None

    if enabled:
        palette = QApplication.palette()
        dark = palette.window().color().lightness() < DARK_PALETTE_LIGHTNESS_THRESHOLD
        rules = get_touch_style(palette, dark)

    apply_style_sheet_block(TOUCH_STYLE_START_MARKER, TOUCH_STYLE_END_MARKER, rules)


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

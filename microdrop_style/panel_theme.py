# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's colours and style sheets for the current theme.

The theme has ONE source: the application palette (``theme_palette()``).
A widget's own palette is not used to decide the theme: a style sheet set
on a widget detaches its palette, which then keeps the old theme's colours
after a switch. Every function takes the palette it resolves against, so
tests can ask with a palette of either theme.
"""

# Enthought library imports.
from pyface.qt import QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.color_contrast import blend, readable_on
from microdrop_style.colors import WHITE
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.palette_helpers import (
    css,
    glyph_pixmap,
    is_dark,
    mix,
    with_alpha,
)

# Local imports.
from . import colour_roles
from .touch_style import TOUCH_GROWS_PROPERTY

_ROLE = QtGui.QPalette.ColorRole


def theme_palette():
    """The palette every colour of the drawer, toasts and bell derives from."""
    return QtWidgets.QApplication.palette()


def theme_of(palette):
    """``colour_roles.LIGHT`` or ``DARK`` for ``palette``."""
    return colour_roles.DARK if is_dark(palette) else colour_roles.LIGHT


def role_color(palette, role):
    """A colour role's ``(light, dark)`` pair for the theme of ``palette``."""
    return QtGui.QColor(role[theme_of(palette)])


def text_contrast(palette):
    """The least contrast accent-coloured text needs in this theme."""
    return colour_roles.TEXT_CONTRAST[theme_of(palette)]


def card_fill(palette, hovered=False):
    """A card's fill: a step lighter than the drawer in either theme."""
    window = palette.color(_ROLE.Window)

    if is_dark(palette):
        return mix(window, WHITE, 0.07 if hovered else 0.045)

    return mix(palette.color(_ROLE.Base), window, 0.35 if hovered else 0.0)


def card_border(palette):
    """A card's hairline border: firmer on light, where a faint one is lost
    against white panes."""
    return with_alpha(palette.color(_ROLE.Text), 0.16 if is_dark(palette) else 0.18)


def muted_text(palette):
    """Secondary text: times, sources, hints."""
    return mix(
        palette.color(_ROLE.Text), palette.color(_ROLE.Window), colour_roles.MUTED_MIX
    )


def link_color(palette):
    """The one colour of clickable text that is not a primary button."""
    return role_color(palette, colour_roles.LINK)


def readable_accent(color, palette):
    """``color`` made readable as text on a card of ``palette``'s theme."""
    surface = colour_roles.surfaces(theme_of(palette))["card"]

    return QtGui.QColor(
        readable_on(QtGui.QColor(color).name(), surface, text_contrast(palette))
    )


def readable_text(color, palette, on_card=False):
    """``color`` made readable as text on a card, or on every surface of the
    drawer (its translucent part at its worst included)."""
    surfaces = colour_roles.surfaces(theme_of(palette))
    names = (
        ["card"] if on_card else ["drawer", "drawer over black", "drawer over white"]
    )
    color = QtGui.QColor(color).name()

    for name in names:
        color = readable_on(color, surfaces[name], text_contrast(palette))

    return QtGui.QColor(color)


def chip_tint(palette):
    """How strongly an accent tints its chip in this theme."""
    return colour_roles.CHIP_TINT[theme_of(palette)]


def disc_tint(palette):
    """How strongly an accent tints its header's glyph disc."""
    return colour_roles.DISC_TINT[theme_of(palette)]


def chip_text(accent, palette):
    """``accent`` readable on its own tinted chip, on every surface of the
    drawer at its worst."""
    theme = theme_of(palette)
    surfaces = colour_roles.surfaces(theme)
    accent = QtGui.QColor(accent).name()
    color = accent

    for surface in surfaces.values():
        chip = blend(accent, surface, chip_tint(palette))
        color = readable_on(color, chip, text_contrast(palette))

    return QtGui.QColor(color)


def accent_of(pair, palette):
    """A ``(light, dark)`` accent pair's colour for ``palette``'s theme."""
    return QtGui.QColor(pair[theme_of(palette)])


# ---------------------------------------------------------------------------
# Style sheets
# ---------------------------------------------------------------------------


def primary_button_style(palette, selector="QPushButton"):
    """A filled button for the card's main action."""
    theme = theme_of(palette)

    return (
        f"{selector} {{"
        f" background: {colour_roles.PRIMARY_FILL[theme]};"
        f" color: {colour_roles.PRIMARY_LABEL[theme]}; border: none;"
        " border-radius: 5px; padding: 4px 12px; font-weight: 600; }"
        f" {selector}:hover {{ background: {colour_roles.PRIMARY_FILL_HOVER[theme]}; }}"
        f" {selector}:pressed {{"
        f" background: {colour_roles.PRIMARY_FILL_PRESSED[theme]}; }}"
    )


def quiet_button_style(palette, selector="QPushButton"):
    """An outlined button for a second action such as "Later"."""
    text = palette.color(_ROLE.Text)

    return (
        f"{selector} {{"
        f" background: transparent; color: {css(text)};"
        f" border: 1px solid {css(with_alpha(text, 0.28))};"
        " border-radius: 5px; padding: 3px 11px; }"
        f" {selector}:hover {{ background: {css(with_alpha(text, 0.07))}; }}"
        f" {selector}:pressed {{ background: {css(with_alpha(text, 0.14))}; }}"
    )


def outlined_button_style(palette, selector="QPushButton"):
    """An outlined button in the link colour: a card's one control when it
    is guidance rather than a command, e.g. "How to calibrate"."""
    color = css(readable_accent(link_color(palette), palette))
    muted = css(with_alpha(muted_text(palette), 0.6))

    return (
        f"{selector} {{"
        f" background: transparent; color: {color}; border: 1px solid {color};"
        " border-radius: 5px; padding: 3px 11px 3px 8px; font-weight: 600; }"
        f" {selector}:hover {{ background: {css(with_alpha(color, 0.10))}; }}"
        f" {selector}:pressed {{ background: {css(with_alpha(color, 0.18))}; }}"
        f" {selector}:disabled {{ color: {muted}; border-color: {muted}; }}"
    )


def outlined_button_icon(glyph, palette, ratio=1.0):
    """``glyph`` in the outlined button's colour."""
    color = readable_accent(link_color(palette), palette)

    return QtGui.QIcon(glyph_pixmap(glyph, 16, color, ratio))


def link_button_style(palette, accent, selector="QPushButton"):
    """A button that reads as a link, e.g. "How do I…?" or "Show more"."""
    color = readable_accent(accent, palette)
    muted = css(with_alpha(muted_text(palette), 0.6))

    return (
        f"{selector} {{"
        f" background: transparent; color: {css(color)}; border: none;"
        " padding: 3px 2px; text-align: left; }"
        f" {selector}:hover {{ text-decoration: underline; }}"
        f" {selector}:disabled {{ color: {muted}; }}"
    )


def icon_button_style(palette, pixel_size=18, selector="QToolButton"):
    """A borderless glyph button, e.g. a card's dismiss cross."""
    text = palette.color(_ROLE.Text)

    return (
        f"{selector} {{"
        f" font-family: '{ICON_FONT_FAMILY}'; font-size: {pixel_size}px;"
        f" color: {css(muted_text(palette))}; background: transparent;"
        " border: none; border-radius: 4px; padding: 2px; }"
        f" {selector}:hover {{ color: {css(text)};"
        f" background: {css(with_alpha(text, 0.08))}; }}"
        f" {selector}:pressed {{ background: {css(with_alpha(text, 0.15))}; }}"
        f" {selector}:disabled {{ color: {css(with_alpha(text, 0.22))}; }}"
    )


def isolated_style_sheet(root, palette):
    """The rules for everything under the widget named ``root`` (an object
    name): the panel's own values for every property the application style
    sheet sets app-wide (touch mode's finger sizes and frames), so none of
    them reaches it. A widget's own style sheet still wins over these; an
    ancestor's (this one) wins over the application's whatever its
    specificity."""
    scope = f"#{root}"
    grows = f'{TOUCH_GROWS_PROPERTY}="true"'
    text = palette.color(_ROLE.Text)
    frame = css(card_border(palette))

    return f"""
{scope} QPushButton[{grows}] {{ padding: 3px 11px; }}
{scope} QToolButton[{grows}] {{ padding: 2px; }}
{scope} QLineEdit[{grows}] {{ padding: 1px 2px; }}
{scope} QCheckBox, {scope} QRadioButton {{ spacing: 6px; padding: 0px; }}
{scope} QCheckBox::indicator, {scope} QRadioButton::indicator {{
    width: 14px; height: 14px;
}}
{scope} QComboBox, {scope} QAbstractSpinBox {{
    min-height: 0px; padding: 1px 4px;
}}
{scope} QHeaderView::section {{
    padding: 3px 6px; border: none;
    border-right: 1px solid {frame}; border-bottom: 1px solid {frame};
    background-color: {css(card_fill(palette))}; color: {css(text)};
}}
{scope} QTableView::item, {scope} QTreeView::item, {scope} QListView::item {{
    min-height: 0px;
}}
{scope} QScrollBar:vertical {{
    width: 8px; margin: 0px; border: none; background-color: transparent;
}}
{scope} QScrollBar:horizontal {{
    height: 8px; margin: 0px; border: none; background-color: transparent;
}}
{scope} QScrollBar::handle {{
    margin: 2px; border-radius: 2px;
    background-color: {css(with_alpha(text, 0.28))};
}}
{scope} QScrollBar::handle:hover, {scope} QScrollBar::handle:pressed {{
    background-color: {css(with_alpha(text, 0.45))};
}}
{scope} QScrollBar::handle:vertical {{ min-height: 24px; }}
{scope} QScrollBar::handle:horizontal {{ min-width: 24px; }}
{scope} QScrollBar::add-line, {scope} QScrollBar::sub-line {{
    width: 0px; height: 0px; border: none; background: none;
}}
{scope} QScrollBar::add-page, {scope} QScrollBar::sub-page {{ background: none; }}
"""

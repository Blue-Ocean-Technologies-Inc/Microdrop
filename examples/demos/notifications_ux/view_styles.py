# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Colours, fonts and style sheets shared by the prototype's views, derived
from the palette so every view follows the light and dark themes.

A candidate for ``microdrop_style`` once ported.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui

# Microdrop style imports.
from microdrop_style.colors import PRIMARY_SHADE, WHITE
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY

_ROLE = QtGui.QPalette.ColorRole

#: Window lightness below which a palette is dark.
DARK_LIGHTNESS = 128

#: Least contrast ratio of accent-coloured text against a card.
ACCENT_TEXT_CONTRAST = 3.2

#: Corner radius (px) of cards, toasts and section headers.
CARD_RADIUS = 8

#: The primary buttons' fill, and while hovered or pressed.
PRIMARY_FILL = PRIMARY_SHADE[600]
PRIMARY_FILL_HOVER = PRIMARY_SHADE[500]
PRIMARY_FILL_PRESSED = PRIMARY_SHADE[800]


#: Logo pictures scaled so far, by path, height and pixel ratio.
_LOGOS = {}


def scaled_logo(path, height, ratio=1.0):
    """The picture at ``path`` ``height`` px tall at its own width, smoothly
    scaled once and kept."""
    key = (str(path), height, ratio)
    logo = _LOGOS.get(key)

    if logo is None:
        logo = QtGui.QPixmap(str(path)).scaledToHeight(
            int(round(height * ratio)),
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        logo.setDevicePixelRatio(ratio)
        _LOGOS[key] = logo

    return logo


def tinted(pixmap, color):
    """``pixmap``'s shape filled with ``color``: a one-colour mark that
    reads on either theme."""
    result = QtGui.QPixmap(pixmap.size())
    result.setDevicePixelRatio(pixmap.devicePixelRatio())
    result.fill(QtCore.Qt.GlobalColor.transparent)

    painter = QtGui.QPainter(result)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QtGui.QColor(color))
    painter.end()

    return result


def is_dark(palette):
    """Whether ``palette`` is a dark one."""
    return palette.color(_ROLE.Window).lightness() < DARK_LIGHTNESS


def mix(first, second, amount):
    """``first`` moved ``amount`` (0-1) of the way to ``second``."""
    first, second = QtGui.QColor(first), QtGui.QColor(second)

    return QtGui.QColor.fromRgbF(
        first.redF() + (second.redF() - first.redF()) * amount,
        first.greenF() + (second.greenF() - first.greenF()) * amount,
        first.blueF() + (second.blueF() - first.blueF()) * amount,
        first.alphaF() + (second.alphaF() - first.alphaF()) * amount,
    )


def with_alpha(color, alpha):
    """``color`` at opacity ``alpha`` (0-1)."""
    color = QtGui.QColor(color)
    color.setAlphaF(alpha)

    return color


def css(color):
    """``color`` as a style-sheet ``rgba()``."""
    color = QtGui.QColor(color)

    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def drawer_fill(palette):
    """The drawer's background: the window colour."""
    return palette.color(_ROLE.Window)


def card_fill(palette, hovered=False):
    """A card's fill: a step lighter than the drawer in either theme, as a
    raised surface."""
    window = palette.color(_ROLE.Window)

    if is_dark(palette):
        fill = mix(window, WHITE, 0.07 if hovered else 0.045)

    else:
        fill = mix(palette.color(_ROLE.Base), window, 0.35 if hovered else 0.0)

    return fill


def card_border(palette):
    """A card's hairline border."""
    return with_alpha(palette.color(_ROLE.Text), 0.16 if is_dark(palette) else 0.11)


def muted_text(palette):
    """Secondary text: times, sources, hints."""
    return mix(palette.color(_ROLE.Text), palette.color(_ROLE.Window), 0.42)


def _luminance(color):
    channels = []

    for value in (color.redF(), color.greenF(), color.blueF()):
        if value <= 0.03928:
            channels.append(value / 12.92)

        else:
            channels.append(((value + 0.055) / 1.055) ** 2.4)

    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(first, second):
    """The WCAG contrast ratio of two colours."""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)

    return (lighter + 0.05) / (darker + 0.05)


def readable_accent(color, palette):
    """``color`` darkened (light theme) or lightened (dark theme) until it
    reads as text on a card."""
    color = QtGui.QColor(color)
    background = card_fill(palette)
    target = QtGui.QColor(WHITE) if is_dark(palette) else QtGui.QColor("#000000")

    for _step in range(10):
        if contrast(color, background) >= ACCENT_TEXT_CONTRAST:
            break

        color = mix(color, target, 0.15)

    return color


def icon_font(pixel_size):
    """The Material Symbols font at ``pixel_size``."""
    font = QtGui.QFont(ICON_FONT_FAMILY)
    font.setPixelSize(pixel_size)

    return font


def text_font(base, point_delta=0.0, weight=None):
    """``base`` resized by ``point_delta`` points, at ``weight``."""
    font = QtGui.QFont(base)

    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() + point_delta)

    if weight is not None:
        font.setWeight(weight)

    return font


def rounded_path(rect, radius=CARD_RADIUS):
    """A rounded rectangle path inside ``rect`` (a QRect), half a pixel in so
    a one-pixel border is crisp."""
    path = QtGui.QPainterPath()
    path.addRoundedRect(
        QtCore.QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius
    )

    return path


def primary_button_style(selector="QPushButton"):
    """A filled button for the card's main action."""
    return (
        f"{selector} {{"
        f" background: {PRIMARY_FILL}; color: {WHITE}; border: none;"
        " border-radius: 5px; padding: 4px 12px; font-weight: 600; }"
        f" {selector}:hover {{ background: {PRIMARY_FILL_HOVER}; }}"
        f" {selector}:pressed {{ background: {PRIMARY_FILL_PRESSED}; }}"
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
    """An outlined button in the primary colour: a card's one control when
    it is guidance rather than a command, e.g. "How to calibrate"."""
    color = css(readable_accent(PRIMARY_FILL, palette))

    return (
        f"{selector} {{"
        f" background: transparent; color: {color}; border: 1px solid {color};"
        " border-radius: 5px; padding: 3px 11px 3px 8px; font-weight: 600; }"
        f" {selector}:hover {{ background: {css(with_alpha(color, 0.10))}; }}"
        f" {selector}:pressed {{ background: {css(with_alpha(color, 0.18))}; }}"
    )


#: Glyph pictures made so far, by glyph, size, colour and pixel ratio.
_GLYPHS = {}


def glyph_pixmap(glyph, pixel_size, color, ratio=1.0):
    """A Material Symbols ``glyph`` drawn in ``color``, for a button's icon."""
    key = (glyph, pixel_size, QtGui.QColor(color).rgba(), ratio)
    pixmap = _GLYPHS.get(key)

    if pixmap is None:
        side = int(round(pixel_size * ratio))
        pixmap = QtGui.QPixmap(side, side)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setFont(icon_font(pixel_size))
        painter.setPen(QtGui.QColor(color))
        painter.drawText(
            QtCore.QRectF(0, 0, pixel_size, pixel_size),
            QtCore.Qt.AlignmentFlag.AlignCenter,
            glyph,
        )
        painter.end()
        _GLYPHS[key] = pixmap

    return pixmap


def outlined_button_icon(glyph, palette, ratio=1.0):
    """``glyph`` in the outlined button's colour."""
    return QtGui.QIcon(
        glyph_pixmap(glyph, 16, readable_accent(PRIMARY_FILL, palette), ratio)
    )


def link_button_style(palette, accent, selector="QPushButton"):
    """A button that reads as a link, e.g. "How do I…?" or "Show more"."""
    color = readable_accent(accent, palette)

    return (
        f"{selector} {{"
        f" background: transparent; color: {css(color)}; border: none;"
        " padding: 3px 2px; text-align: left; }"
        f" {selector}:hover {{ text-decoration: underline; }}"
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

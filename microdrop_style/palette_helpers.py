# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Small Qt colour, font and picture helpers for painted widgets that follow
the light and dark themes: palette darkness, colour mixing, style-sheet
colours, the icon font, scaled and tinted pictures, and the pill shape of a
chip.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui

# Local imports.
from .fonts.fontnames import ICON_FONT_FAMILY

_ROLE = QtGui.QPalette.ColorRole

#: Window lightness below which a palette is dark (as ``helpers``).
DARK_LIGHTNESS = 128

#: A chip's room around its text (px): above and below, and either side.
CHIP_PADDING = (2, 9)

#: Pictures made so far, by what they were made from.
_LOGOS = {}
_GLYPHS = {}


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


def icon_font(pixel_size):
    """The Material Symbols font at ``pixel_size``."""
    font = QtGui.QFont(ICON_FONT_FAMILY)
    font.setPixelSize(pixel_size)

    return font


def rounded_path(rect, radius):
    """A rounded rectangle path inside ``rect`` (a QRect), half a pixel in so
    a one-pixel border is crisp."""
    path = QtGui.QPainterPath()
    path.addRoundedRect(
        QtCore.QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius
    )

    return path


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
    """``pixmap``'s shape filled with ``color``: a one-colour mark that reads
    on either theme."""
    result = QtGui.QPixmap(pixmap.size())
    result.setDevicePixelRatio(pixmap.devicePixelRatio())
    result.fill(QtCore.Qt.GlobalColor.transparent)

    painter = QtGui.QPainter(result)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QtGui.QColor(color))
    painter.end()

    return result


def glyph_pixmap(glyph, pixel_size, color, ratio=1.0):
    """A Material Symbols ``glyph`` drawn in ``color``, e.g. for a button's
    icon; made once per glyph, size, colour and pixel ratio."""
    key = (glyph, pixel_size, QtGui.QColor(color).rgba(), ratio)
    pixmap = _GLYPHS.get(key)

    if pixmap is not None:
        return pixmap

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


def style_chip(widget, rules, more=""):
    """Give ``widget`` (a label or button, its font set) a chip's pill shape:
    exactly as tall as its text needs, its corners half that height. A fixed
    radius larger than half the height makes Qt draw no rounding at all.
    ``rules`` are the chip's colour declarations; ``more`` further rules for
    its states, e.g. ``QPushButton:checked``."""
    height = QtGui.QFontMetrics(widget.font()).height() + 2 * CHIP_PADDING[0] + 2
    selector = widget.metaObject().className()

    widget.setFixedHeight(height)
    widget.setStyleSheet(
        f"{selector} {{ {rules} border-radius: {height // 2}px;"
        f" padding: 0px {CHIP_PADDING[1]}px; }} {more}"
    )

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Trace the app's icon-font glyphs into SVG, for tutorial toolbar sections.

A glyph is named either by its ``ICON_*`` constant in
``microdrop_style.icons.icons`` (``ICON_DROP_EC``) or by the Material Symbols
ligature the app's widgets use directly (``live_tv``). Both map to one SVG id:
the constant name without ``ICON_``, lower-cased (``drop_ec``), or the
ligature itself. Tracing goes through Qt's own text outlining of the font the
app draws its buttons with, so it needs a ``QGuiApplication`` (one is created
when missing; set ``QT_QPA_PLATFORM=offscreen`` to run without a display).
"""

# Standard library imports.
import html
import re
import sys

# Enthought library imports.
from pyface.qt.QtCore import QPointF
from pyface.qt.QtGui import QFont, QFontMetricsF, QGuiApplication, QPainterPath

# Microdrop style imports.
from microdrop_style.font_paths import load_font_and_get_family
from microdrop_style.icons import icons

GLYPH_PIXEL_SIZE = 48
ICON_FONT_NAME = "material_symbols"
ICON_PREFIX = "ICON_"
SYMBOL_PATTERN = re.compile(
    r'<symbol id="ic-(?P<id>[A-Za-z0-9_]+)" viewBox="(?P<viewBox>[^"]*)" '
    r'data-text="(?P<text>[^"]*)"><path d="(?P<d>[^"]*)"/></symbol>'
)


def glyph_id(name):
    """Return the SVG symbol id (without ``ic-``) for a glyph name."""
    if name.startswith(ICON_PREFIX):
        return name[len(ICON_PREFIX) :].lower()

    return name


def glyph_text(name):
    """Return the font text drawn for a glyph name or id.

    An ``ICON_*`` name must exist; a bare id resolves to its ``ICON_*``
    constant when there is one, else it is taken as a ligature name.
    """
    if name.startswith(ICON_PREFIX):
        return getattr(icons, name)

    return getattr(icons, ICON_PREFIX + name.upper(), name)


def path_data(path):
    """Return the SVG ``d`` attribute for a QPainterPath of lines and cubics."""
    commands = []
    index = 0

    while index < path.elementCount():
        element = path.elementAt(index)

        if element.type == QPainterPath.ElementType.MoveToElement:
            commands.append(f"M{element.x:.2f} {element.y:.2f}")
            index += 1

        elif element.type == QPainterPath.ElementType.LineToElement:
            commands.append(f"L{element.x:.2f} {element.y:.2f}")
            index += 1

        elif element.type == QPainterPath.ElementType.CurveToElement:
            control = path.elementAt(index + 1)
            end = path.elementAt(index + 2)
            commands.append(
                f"C{element.x:.2f} {element.y:.2f} {control.x:.2f} {control.y:.2f} "
                f"{end.x:.2f} {end.y:.2f}"
            )
            index += 3

        else:
            index += 1

    return "".join(commands).replace(".00", "")


def trace_glyphs(names, pixel_size=GLYPH_PIXEL_SIZE):
    """Trace glyphs into ``{id: {"text", "d", "viewBox"}}``.

    ``viewBox`` frames the font's em square, so every glyph sits in the box
    the app's buttons draw it in. Raises ``ValueError`` for a ligature the
    font does not have (Qt would otherwise outline its letters).
    """
    # Font loading needs a live QGuiApplication for the whole run.
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841

    font = QFont(load_font_and_get_family(ICON_FONT_NAME))
    font.setPixelSize(pixel_size)
    metrics = QFontMetricsF(font)
    em_top = metrics.ascent() - pixel_size
    traced = {}

    for name in names:
        text = glyph_text(name)
        advance = metrics.horizontalAdvance(text)

        if len(text) > 1 and advance > 1.5 * pixel_size:
            raise ValueError(f"The icon font has no glyph for ligature '{text}'")

        path = QPainterPath()
        path.addText(QPointF(0, metrics.ascent()), font, text)

        traced[glyph_id(name)] = {
            "text": text,
            "d": path_data(path),
            "viewBox": f"0 {em_top:g} {advance:g} {pixel_size}",
        }

    return traced


def symbol_markup(symbol_id, glyph):
    """Return the ``<symbol>`` element for a traced glyph.

    ``data-text`` keeps the font text it was traced from, so the built page
    doubles as the glyph cache for its next build (see ``read_symbols``).
    """
    text = html.escape(glyph["text"], quote=True)

    return (
        f'<symbol id="ic-{symbol_id}" viewBox="{glyph["viewBox"]}" '
        f'data-text="{text}"><path d="{glyph["d"]}"/></symbol>'
    )


def read_symbols(page):
    """Return ``{id: {"text", "d", "viewBox"}}`` for the glyph symbols a built
    page holds."""
    return {
        match["id"]: {
            "text": html.unescape(match["text"]),
            "d": match["d"],
            "viewBox": match["viewBox"],
        }
        for match in SYMBOL_PATTERN.finditer(page)
    }

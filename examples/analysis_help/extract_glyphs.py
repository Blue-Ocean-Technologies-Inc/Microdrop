# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Regenerate the SVG glyph paths of the analysis help guide's toolbar icons.

Traces each Material Symbols glyph the guide's Toolbar icons section shows,
through Qt's own text outlining, into SVG path data. Writes ``glyphs.json``
mapping glyph name to ``{"d", "adv", "h", "bbox"}`` (path data, advance
width, line height and bounding box, at a 48 px font size).

Output goes to ``image_viewer/resources/analysis_help/glyphs.json`` (next to
the help HTML) unless an output folder is given. From ``src``::

    pixi run python -m examples.analysis_help.extract_glyphs [out_dir]

Set ``QT_QPA_PLATFORM=offscreen`` to run without a display.
"""

# Standard library imports.
import json
import sys
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtCore import QPointF
from pyface.qt.QtGui import QFont, QFontMetricsF, QGuiApplication, QPainterPath

# Microdrop package imports.
from image_viewer.consts import ANALYSIS_HELP_HTML_PATH

# Microdrop style imports.
from microdrop_style.font_paths import load_font_and_get_family
from microdrop_style.icons.icons import (
    ICON_ADJUST,
    ICON_CANCEL,
    ICON_CAPSULE,
    ICON_CHEVRON_LEFT,
    ICON_CHEVRON_RIGHT,
    ICON_CIRCLE,
    ICON_CONTOUR,
    ICON_COPY,
    ICON_CROP,
    ICON_DELETE,
    ICON_DELETE_SWEEP,
    ICON_EDIT,
    ICON_FIT_SCREEN,
    ICON_FOLDER_OPEN,
    ICON_FUNCTION,
    ICON_HOME,
    ICON_NEXT,
    ICON_OPEN_IN_NEW,
    ICON_PASTE,
    ICON_PAUSE,
    ICON_PLAY,
    ICON_PREVIOUS,
    ICON_RECTANGLE,
    ICON_REFRESH,
    ICON_RESET_WRENCH,
    ICON_RULER,
    ICON_SAVE,
    ICON_SHOW_CHART,
    ICON_TONALITY,
    ICON_TRANSFORM,
    ICON_VIEW_3D,
    ICON_VISIBILITY,
    ICON_VISIBILITY_OFF,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

DEFAULT_OUTPUT_DIR = ANALYSIS_HELP_HTML_PATH.parent / "analysis_help"
GLYPH_PIXEL_SIZE = 48

#: Glyph name -> font text. Glyphs without an ICON_* constant are the
#: ligature names the app's widgets use directly.
GLYPHS = {
    "folder_open": ICON_FOLDER_OPEN,
    "home": ICON_HOME,
    "open_in_new": ICON_OPEN_IN_NEW,
    "refresh": ICON_REFRESH,
    "zoom_in": "zoom_in",
    "zoom_out": "zoom_out",
    "previous": ICON_PREVIOUS,
    "play_arrow": ICON_PLAY,
    "pause": ICON_PAUSE,
    "next": ICON_NEXT,
    "show_chart": ICON_SHOW_CHART,
    "reset_wrench": ICON_RESET_WRENCH,
    "save": ICON_SAVE,
    "delete_sweep": ICON_DELETE_SWEEP,
    "chevron_left": ICON_CHEVRON_LEFT,
    "chevron_right": ICON_CHEVRON_RIGHT,
    "expand_more": "expand_more",
    "circle": ICON_CIRCLE,
    "rectangle": ICON_RECTANGLE,
    "pill": ICON_CAPSULE,
    "pentagon": ICON_CONTOUR,
    "straighten": ICON_RULER,
    "tonality": ICON_TONALITY,
    "adjust": ICON_ADJUST,
    "view_in_ar": ICON_VIEW_3D,
    "transform": ICON_TRANSFORM,
    "crop": ICON_CROP,
    "edit": ICON_EDIT,
    "delete": ICON_DELETE,
    "content_copy": ICON_COPY,
    "content_paste": ICON_PASTE,
    "wand_shine": "wand_shine",
    "eye_tracking": "eye_tracking",
    "ink_highlighter_move": "ink_highlighter_move",
    "cancel": ICON_CANCEL,
    "visibility": ICON_VISIBILITY,
    "visibility_off": ICON_VISIBILITY_OFF,
    "function": ICON_FUNCTION,
    "reset_focus": "reset_focus",
    "rotate_90_degrees_cw": "rotate_90_degrees_cw",
    "fit_screen": ICON_FIT_SCREEN,
}


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


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    # Font loading needs a live QGuiApplication for the whole run.
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841

    font = QFont(load_font_and_get_family("material_symbols"))
    font.setPixelSize(GLYPH_PIXEL_SIZE)
    metrics = QFontMetricsF(font)
    glyphs = {}

    for name, text in GLYPHS.items():
        path = QPainterPath()
        path.addText(QPointF(0, metrics.ascent()), font, text)
        box = path.boundingRect()

        glyphs[name] = {
            "d": path_data(path),
            "adv": metrics.horizontalAdvance(text),
            "h": metrics.height(),
            "bbox": [box.x(), box.y(), box.width(), box.height()],
        }

    target = out / "glyphs.json"
    target.write_text(json.dumps(glyphs), encoding="utf-8")
    logger.info(f"{target}: {len(glyphs)} glyphs, {target.stat().st_size} bytes")


if __name__ == "__main__":
    main()

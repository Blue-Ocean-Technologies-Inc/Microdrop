# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""
Dock-pane separator styling: the QMainWindow dock-splitter handle colour, and
a finger-hittable thickness for touchscreen rigs.
"""

# Local imports.
from .colors import ACCENT_COLOR, GREY

# Separator thickness in pixels, wide enough for a fingertip on the
# portable rig's touchscreen. Applied to both orientations.
SEPARATOR_THICKNESS = 10

# Separator colour per theme, used unless a custom colour is chosen.
DOCK_SEPARATOR_THEME_COLORS = {"light": GREY["light"], "dark": GREY["dark"]}


def get_dock_separator_style(color, thickness=None):
    """Return the QSS for QMainWindow dock separators.

    Parameters
    ----------
    color : str
        Resting separator colour, any QSS colour string.
    thickness : int, optional
        Separator width and height in pixels; None keeps the native extent.
    """
    size_rules = ""

    if thickness is not None:
        size_rules = f"\n    width: {thickness}px;\n    height: {thickness}px;"

    return f"""
QMainWindow::separator {{
    background-color: {color};{size_rules}
}}

QMainWindow::separator:hover {{
    background-color: {ACCENT_COLOR};
}}
"""

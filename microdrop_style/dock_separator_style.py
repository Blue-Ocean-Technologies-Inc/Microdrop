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
Dock-pane separator styling for touchscreen rigs.
Widens QMainWindow dock-splitter handles so they are finger-hittable.
"""

from .colors import ACCENT_COLOR, GREY

# Separator thickness in pixels, wide enough for a fingertip on the
# portable rig's touchscreen. Applied to both orientations.
SEPARATOR_THICKNESS = 10

# Light mode dock separator styles
LIGHT_MODE_DOCK_SEPARATOR_STYLE = f"""
QMainWindow::separator {{
    background-color: {GREY["light"]};
    width: {SEPARATOR_THICKNESS}px;
    height: {SEPARATOR_THICKNESS}px;
}}

QMainWindow::separator:hover {{
    background-color: {ACCENT_COLOR};
}}
"""

# Dark mode dock separator styles
DARK_MODE_DOCK_SEPARATOR_STYLE = f"""
QMainWindow::separator {{
    background-color: {GREY["dark"]};
    width: {SEPARATOR_THICKNESS}px;
    height: {SEPARATOR_THICKNESS}px;
}}

QMainWindow::separator:hover {{
    background-color: {ACCENT_COLOR};
}}
"""


def get_dock_separator_style(theme="light"):
    """
    Get dock-pane separator style based on theme.

    Args:
        theme (str): 'light' or 'dark'

    Returns:
        str: QSS stylesheet for QMainWindow dock separators
    """
    if theme == "dark":
        return DARK_MODE_DOCK_SEPARATOR_STYLE
    else:
        return LIGHT_MODE_DOCK_SEPARATOR_STYLE

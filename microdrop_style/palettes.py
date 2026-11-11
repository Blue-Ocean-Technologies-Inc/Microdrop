# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Application palettes for platforms whose theme cannot switch colour scheme."""

# Enthought library imports.
from pyface.qt.QtGui import QColor, QPalette

# Local imports.
from .colors import ERROR_COLOR, GREY, INFO_COLOR, PRIMARY_COLOR, WHITE


def dark_palette():
    """Return the Fusion-style dark palette in Microdrop colours."""
    palette = QPalette()
    roles = QPalette.ColorRole

    role_colors = {
        roles.Window: GREY["darker"],
        roles.WindowText: WHITE,
        roles.Base: GREY["darkest"],
        roles.AlternateBase: GREY["darker"],
        roles.ToolTipBase: GREY["darkest"],
        roles.ToolTipText: WHITE,
        roles.Text: WHITE,
        roles.Button: GREY["darker"],
        roles.ButtonText: WHITE,
        roles.BrightText: ERROR_COLOR,
        roles.Link: INFO_COLOR,
        roles.Highlight: PRIMARY_COLOR,
        roles.HighlightedText: WHITE,
    }

    for role, color in role_colors.items():
        palette.setColor(role, QColor(color))

    for role in (roles.WindowText, roles.Text, roles.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(GREY["dark"]))

    return palette

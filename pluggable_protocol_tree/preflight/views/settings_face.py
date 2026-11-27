# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The card's settings face: the ack-wait grid of the live protocol
preferences, edited in place, and a link to every protocol setting.

The grid is the Settings dialog's own section (``ack_times_view``), so
there is one editor definition and no copy of the values: an edit reaches
the column handlers at once, through the dock pane's ack-time sync.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop package imports.
from pluggable_protocol_tree.services.preferences import ack_times_view

# Microdrop style imports.
from microdrop_style.panel_metrics import DRAWER_PADDING_PX
from microdrop_style.panel_theme import link_button_style, link_color
from microdrop_style.typography import CARD_TITLE, META, role_font

# Local imports.
from .panel_parts import icon_button
from .view_consts import ICON_BACK, ROW_HEIGHT

#: The face's title.
TITLE_TEXT = "Ack wait times"

_ALIGN = QtCore.Qt.AlignmentFlag


def settings_face(preferences, palette, on_back, on_all_settings):
    """The settings face over ``preferences`` and the TraitsUI ``ui`` of
    its embedded grid, which the caller disposes when the face goes.

    Parameters
    ----------
    on_back : callable
        Returns the card to the checks.
    on_all_settings : callable
        Asks for the Settings dialog on the Protocol Settings tab.
    """
    face = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(face)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(DRAWER_PADDING_PX)

    ui = preferences.edit_traits(view=ack_times_view, parent=face, kind="subpanel")
    _fit_tables(ui.control)

    link = QtWidgets.QPushButton("All protocol settings…")
    link.setFont(role_font(META))
    link.setStyleSheet(link_button_style(palette, link_color(palette)))
    link.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    link.clicked.connect(on_all_settings)

    layout.addWidget(_title_row(palette, on_back))
    layout.addWidget(ui.control)
    layout.addWidget(link, 0, _ALIGN.AlignLeft)

    return face, ui


def _title_row(palette, on_back):
    """The back arrow and the title, as high as the checks' header."""
    widget = QtWidgets.QWidget()
    widget.setFixedHeight(ROW_HEIGHT)
    row = QtWidgets.QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 6, 0)
    row.setSpacing(2)

    title = QtWidgets.QLabel(TITLE_TEXT)
    title.setFont(role_font(CARD_TITLE))

    row.addWidget(icon_button(ICON_BACK, "Back to the checks", palette, on_back))
    row.addWidget(title, 1)

    return widget


def _fit_tables(control):
    """Fix every table under ``control`` to its rows: a table's size hint
    is a fixed 192 px, whatever it holds, which the card would size to."""
    for table in control.findChildren(QtWidgets.QTableWidget):
        table.setFixedHeight(
            table.horizontalHeader().sizeHint().height()
            + table.verticalHeader().length()
            + 2 * table.frameWidth()
        )

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""The "new" marker: a small filled circle in the strong text colour, so
"new" collides with no severity or accent colour."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

#: Diameter (px) of the marker.
NEW_DOT_SIZE = 8


class NewDot(QtWidgets.QWidget):
    """The "new" marker, with a little room around it."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(NEW_DOT_SIZE + 4, NEW_DOT_SIZE + 4)
        self.setToolTip("New since you last opened notifications")

    def paintEvent(self, event):
        # The application's palette: a style sheet detaches a widget's own.
        color = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Text)
        painter = QtGui.QPainter(self)

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QtCore.QRectF(2, 2, NEW_DOT_SIZE, NEW_DOT_SIZE))

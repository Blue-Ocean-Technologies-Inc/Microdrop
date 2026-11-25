# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The fading tint the drawer lays over an item it reveals."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR
from microdrop_style.palette_helpers import with_alpha

# Local imports.
from .view_consts import HIGHLIGHT_MS

#: Corner radius (px) of a highlighted item.
HIGHLIGHT_RADIUS = 8


class Highlight(QtWidgets.QWidget):
    """A tint laid over a revealed item, fading: "this is the one"."""

    def __init__(self, parent):
        super().__init__(parent)

        self.strength = 0.0
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._fade = QtCore.QVariantAnimation(self)
        self._fade.setDuration(HIGHLIGHT_MS)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QtCore.QEasingCurve.Type.InQuad)
        self._fade.valueChanged.connect(self._set_strength)
        self._fade.finished.connect(self.hide)

    def flash(self, rect):
        """Tint ``rect`` (in the parent's coordinates), fading out."""
        self.setGeometry(rect)
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.start()

    def _set_strength(self, value):
        self.strength = value
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(INFO_COLOR, 0.3 * self.strength))
        painter.drawRoundedRect(
            QtCore.QRectF(self.rect()), HIGHLIGHT_RADIUS, HIGHLIGHT_RADIUS
        )

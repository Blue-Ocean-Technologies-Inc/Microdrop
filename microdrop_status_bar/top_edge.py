# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The status bar's top edge: contributed widgets laid along it, full width,
over the bar's contents rather than in its layout (#1211)."""

# Enthought library imports.
from pyface.qt import QtCore


class TopEdgeOverlay(QtCore.QObject):
    """Lays its widgets along ``status_bar``'s top edge, each as tall as its
    own height, and keeps them there as the bar resizes. The widgets are
    transparent to the mouse, so they never take a click from the bar."""

    def __init__(self, status_bar):
        super().__init__(status_bar)

        self._status_bar = status_bar
        self._widgets = []

        status_bar.installEventFilter(self)

    def __contains__(self, widget):
        return widget in self._widgets

    def add(self, widget):
        """Lay ``widget`` along the top edge."""
        widget.setParent(self._status_bar)
        widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._widgets.append(widget)

        self._place(widget)
        widget.show()

    def remove(self, widget):
        """Take ``widget`` off the top edge; the caller deletes it."""
        self._widgets.remove(widget)
        widget.hide()

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.Resize:
            for widget in self._widgets:
                self._place(widget)

        return super().eventFilter(watched, event)

    def _place(self, widget):
        widget.setGeometry(0, 0, self._status_bar.width(), widget.height())
        widget.raise_()

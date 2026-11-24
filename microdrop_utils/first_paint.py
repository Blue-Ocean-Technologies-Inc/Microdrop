# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Run work once a widget has painted for the first time (#1064)."""

# Enthought library imports.
from pyface.api import GUI
from pyface.qt.QtCore import QEvent, QObject


class _FirstPaintWatcher(QObject):
    """Event filter that hands one callback to the event loop on the
    watched widget's first paint, then removes itself."""

    def __init__(self, callback, parent):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, watched, event):

        if event.type() == QEvent.Type.Paint:
            watched.removeEventFilter(self)
            self.deleteLater()

            # A later turn, so the frame being painted reaches the screen
            # before the callback's work starts.
            GUI.invoke_later(self._callback)

        return False


def call_after_first_paint(widget, callback):
    """Call ``callback()`` on the event-loop turn after ``widget`` first
    paints."""
    widget.installEventFilter(_FirstPaintWatcher(callback, widget))

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.qt.QtCore import QEvent, QObject, Qt, QTimer
from pyface.qt.QtGui import QContextMenuEvent, QGuiApplication
from pyface.qt.QtWidgets import QApplication, QWidget


class TouchLongPressRightClickFilter(QObject):
    """Application-level event filter that turns a touch long-press into a
    right click: a left press Qt synthesized from touch, held still past the
    platform press-and-hold interval, posts the QContextMenuEvent a right
    click would to the pressed widget.

    Install on the QApplication instance. Real mouse and pen input never
    arms the timer, and moving past the drag threshold or releasing
    cancels it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = None
        self._pos = None
        self._global_pos = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(
            QGuiApplication.styleHints().mousePressAndHoldInterval()
        )
        self._timer.timeout.connect(self._post_context_menu_event)

    def eventFilter(self, watched, event):
        event_type = event.type()

        if event_type == QEvent.Type.MouseButtonPress:
            if (
                isinstance(watched, QWidget)
                and event.button() == Qt.MouseButton.LeftButton
                and event.source() != Qt.MouseEventSource.MouseEventNotSynthesized
            ):
                self._target = watched
                self._pos = event.position().toPoint()
                self._global_pos = event.globalPosition().toPoint()
                self._timer.start()
        elif event_type == QEvent.Type.MouseMove:
            if self._timer.isActive():
                moved = event.globalPosition().toPoint() - self._global_pos
                if moved.manhattanLength() > QApplication.startDragDistance():
                    self._cancel()
        elif event_type in (
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.TouchCancel,
        ):
            self._cancel()

        return False

    def _cancel(self):
        self._timer.stop()
        self._target = None

    def _post_context_menu_event(self):
        if self._target is None:
            return

        QApplication.postEvent(
            self._target,
            QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse, self._pos, self._global_pos
            ),
        )
        self._target = None

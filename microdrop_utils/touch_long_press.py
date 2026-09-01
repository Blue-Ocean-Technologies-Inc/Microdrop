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
from pyface.qt.QtWidgets import QApplication, QToolTip, QWidget


class TouchLongPressRightClickFilter(QObject):
    """Application-level event filter that turns a touch long-press into a
    right click: a left press Qt synthesized from touch, held still past the
    platform press-and-hold interval, sends the QContextMenuEvent a right
    click would to the pressed widget. When no context menu consumes that
    event, the widget's tooltip is shown at the finger instead once it
    lifts — touchscreens have no hover, so a long-press is how a touch
    user reads any control's tooltip.

    Install on the QApplication instance. Real mouse and pen input never
    arms the timer, and moving past the drag threshold or releasing
    cancels it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = None
        self._pos = None
        self._global_pos = None
        self._pending_tooltip = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(
            QGuiApplication.styleHints().mousePressAndHoldInterval()
        )
        self._timer.timeout.connect(self._post_context_menu_event)

    def eventFilter(self, watched, event):
        event_type = event.type()

        if event_type == QEvent.Type.MouseButtonPress:
            # An unaccepted press is re-delivered to each ancestor widget as
            # it propagates; an active timer means this press already armed
            # on its first, deepest receiver — the context-menu target.
            if (
                isinstance(watched, QWidget)
                and event.button() == Qt.MouseButton.LeftButton
                and event.source() != Qt.MouseEventSource.MouseEventNotSynthesized
                and not self._timer.isActive()
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
        elif event_type == QEvent.Type.MouseButtonRelease:
            self._cancel()
            self._show_pending_tooltip()
        elif event_type == QEvent.Type.TouchCancel:
            self._cancel()
            self._pending_tooltip = None

        return False

    def _cancel(self):
        self._timer.stop()
        self._target = None

    def _post_context_menu_event(self):
        target, pos, global_pos = self._target, self._pos, self._global_pos
        self._target = None
        if target is None:
            return

        menu_event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, global_pos)
        QApplication.sendEvent(target, menu_event)

        if not menu_event.isAccepted() and target.toolTip():
            # No context menu took the long press — surface the widget's
            # tooltip instead, once the finger lifts (shown any earlier,
            # the release event itself hides it again).
            self._pending_tooltip = (global_pos, target.toolTip())

    def _show_pending_tooltip(self):
        if self._pending_tooltip is None:
            return

        global_pos, text = self._pending_tooltip
        self._pending_tooltip = None
        # Deferred a tick so the release finishes dispatching first.
        QTimer.singleShot(0, lambda: QToolTip.showText(global_pos, text))

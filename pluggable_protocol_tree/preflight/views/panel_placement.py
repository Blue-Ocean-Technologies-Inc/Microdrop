# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Where the pre-flight card sits: above its anchor, clamped inside the
window's content rect, kept there as the window and the anchor move, and
closed on Esc or a press outside both."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop style imports.
from microdrop_style.panel_metrics import DRAWER_PADDING_PX

# Local imports.
from .view_consts import ANCHOR_GAP, WINDOW_MARGIN

_EVENT = QtCore.QEvent.Type

#: Window and anchor events after which the open panel is placed again.
_PLACING_EVENTS = (_EVENT.Resize, _EVENT.Move, _EVENT.LayoutRequest, _EVENT.Show)

_PRESSES = (_EVENT.MouseButtonPress, _EVENT.MouseButtonDblClick)


def window_room(window):
    """The window's content rect: all of it below the menu bar."""
    rect = window.rect()
    menu = window.menuWidget() if isinstance(window, QtWidgets.QMainWindow) else None

    if menu is not None and menu.isVisible():
        rect.setTop(menu.geometry().bottom() + 1)

    return rect


class PanelPlacement(QtCore.QObject):
    """Places ``panel``, a child laid over its window, above an anchor.

    One event filter on the window, the anchor and the window's handle:
    window and anchor moves call ``on_moved`` (the panel places itself
    again), and the handle's input closes the open panel on Esc or on a
    press outside the panel and its anchor.
    """

    def __init__(self, panel, on_moved):
        super().__init__(panel)

        self.anchor = None

        self._panel = panel
        self._on_moved = on_moved
        self._handle = None

        if panel.parentWidget() is not None:
            panel.parentWidget().installEventFilter(self)

    def watch(self, anchor):
        """Place above ``anchor`` from now on, and watch the window's input."""
        if anchor is not self.anchor:
            if self.anchor is not None:
                self.anchor.removeEventFilter(self)

            anchor.installEventFilter(self)
            self.anchor = anchor

        handle = self._panel.window().windowHandle()

        if self._handle is None and handle is not None:
            handle.installEventFilter(self)
            self._handle = handle

    def release(self):
        """Remove the event filters from the window, its handle and the
        anchor, as before the panel is deleted."""
        for watched in (self._panel.parentWidget(), self._handle, self.anchor):
            if watched is None:
                continue

            try:
                watched.removeEventFilter(self)

            except RuntimeError:
                # Already deleted with the window: nothing left to filter.
                pass

        self.anchor = None
        self._handle = None

    def target(self, fit_height):
        """The panel's top-left and height: ``fit_height(room)`` of the room
        above the anchor, left edges aligned, WINDOW_MARGIN inside the
        window's content rect."""
        window = self._panel.parentWidget()
        room = window_room(window)
        anchor = self.anchor.mapTo(window, QtCore.QPoint(0, 0))

        top = room.top() + WINDOW_MARGIN
        bottom = min(anchor.y() - ANCHOR_GAP, room.bottom() + 1 - WINDOW_MARGIN)
        height = fit_height(max(bottom - top, 0))

        left = room.left() + WINDOW_MARGIN
        right = room.right() + 1 - WINDOW_MARGIN - self._panel.width()
        end = QtCore.QPoint(
            max(min(anchor.x() - DRAWER_PADDING_PX, right), left),
            max(bottom - height, top),
        )

        return end, height

    def eventFilter(self, watched, event):
        if not self._panel.isVisible():
            return False

        if watched is self._handle:
            return self._on_input(event)

        if event.type() in _PLACING_EVENTS:
            self._on_moved()

        elif (
            event.type() == _EVENT.ChildAdded and watched is self._panel.parentWidget()
        ):
            # Panes added later would cover the panel.
            self._panel.raise_()

        return False

    def _on_input(self, event):
        """Close on Esc, or on a press outside the panel and its anchor,
        which still goes on to what was pressed."""
        if event.type() == _EVENT.KeyPress and event.key() == QtCore.Qt.Key.Key_Escape:
            self._panel.close()

            return True

        if event.type() in _PRESSES:
            window = self._panel.parentWidget()
            point = window.mapFrom(self._panel.window(), event.position().toPoint())
            anchor_top_left = self.anchor.mapTo(window, QtCore.QPoint(0, 0))
            anchor = QtCore.QRect(anchor_top_left, self.anchor.size())
            outside = not self._panel.geometry().contains(point)

            if outside and not anchor.contains(point):
                self._panel.close()

        return False

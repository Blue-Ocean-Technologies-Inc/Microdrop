# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What the open drawer watches, and only while it is open: its main
window's widget events (to stay placed and on top), its main window's own
input (a press outside closes it), and its own repaints (a busy backdrop
turns it opaque).

Nothing here filters the whole application (#1135): a filter on the main
window's QWindow sees only that window's input, and the backdrop is judged
from the drawer's own repaints, which a translucent drawer gets whenever
what lies beneath repaints.
"""

# Standard library imports.
import time
from collections import deque

# Enthought library imports.
from pyface.qt import QtCore, QtGui
from traits.api import Any, Bool, Callable, Float, HasTraits, Instance, List

# Local imports.
from ..models.notifications_pane_model import NotificationsPaneModel
from .view_consts import DRAWER_BACKDROP_PAINTS_PER_S

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Repaints within this many seconds of each other are one window repaint.
BACKDROP_SAME_FRAME_S = 0.015

_PRESSES = (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonDblClick)

#: Window events after which the open drawer is placed again.
_PLACING_EVENTS = (
    QtCore.QEvent.Type.Resize,
    QtCore.QEvent.Type.LayoutRequest,
    QtCore.QEvent.Type.Show,
)


class _EventRelay(QtCore.QObject):
    """An event filter handing the events of what it filters to
    ``handler(watched, event)``."""

    def __init__(self, handler, parent=None):
        super().__init__(parent)

        self._handler = handler

    def eventFilter(self, watched, event):
        return self._handler(watched, event)


class OpenDrawerWatch(HasTraits):
    """Watches a drawer's window and repaints while the drawer is open."""

    #: Its ``is_open`` is set False by a press outside.
    model = Instance(NotificationsPaneModel)

    #: The QMainWindow and the drawer widget on it.
    window = Any()
    drawer = Any()

    #: Widgets whose presses never count as outside the drawer.
    exempt = List()

    #: Whether a press elsewhere in the window closes the drawer.
    closes_on_click_outside = Bool(True)

    #: ``place()`` puts the drawer where it goes; ``busy()`` says whether
    #: the drawer is animating itself (its repaints then do not count).
    place = Callable()
    busy = Callable()

    #: Repaints of the drawer within the last second; repaints before
    #: ``_count_from`` (time.monotonic()) are the drawer opening.
    _paints = Instance(deque, ())
    _count_from = Float()

    #: Whether the release of a press that closed the drawer is still due.
    _swallow_release = Bool(False)

    _window_relay = Any()
    _input_relay = Any()

    def start(self, settle_s):
        """Start watching; repaints count after ``settle_s`` seconds."""
        self._paints.clear()
        self._count_from = time.monotonic() + settle_s

        if self._window_relay is None:
            self._window_relay = _EventRelay(self._on_window_event, self.window)
            self.window.installEventFilter(self._window_relay)

        handle = self.window.windowHandle()

        if self._input_relay is None and handle is not None:
            self._input_relay = _EventRelay(self._on_window_input, self.window)
            handle.installEventFilter(self._input_relay)

    def stop(self):
        """Stop watching, unless the release of a closing press is due: it
        stops once that is used up."""

        if self._swallow_release:
            return

        try:
            if self._window_relay is not None:
                self.window.removeEventFilter(self._window_relay)

            handle = self.window.windowHandle()

            if self._input_relay is not None and handle is not None:
                handle.removeEventFilter(self._input_relay)

        # The window went first; its filters went with it.
        except RuntimeError as error:
            logger.debug(f"Notifications drawer window already deleted: {error}")

        self._window_relay = None
        self._input_relay = None

    @property
    def watching(self):
        """Whether any filter is installed."""
        return self._window_relay is not None or self._input_relay is not None

    def note_paint(self):
        """Turn the drawer opaque once it keeps repainting over a changing
        backdrop: a translucent drawer is repainted with what lies beneath,
        a camera feed's every frame. Its own repaints — opening, easing its
        height, or under the mouse while used — do not count."""
        drawer = self.drawer

        if drawer is None or not drawer.is_translucent():
            return

        now = time.monotonic()
        paints = self._paints
        cursor = drawer.mapFromGlobal(QtGui.QCursor.pos())

        if now < self._count_from or drawer.rect().contains(cursor) or self.busy():
            return

        if paints and now - paints[-1] < BACKDROP_SAME_FRAME_S:
            return

        paints.append(now)

        while paints and now - paints[0] > 1.0:
            paints.popleft()

        if len(paints) > DRAWER_BACKDROP_PAINTS_PER_S:
            logger.debug("Notifications drawer turns opaque over a busy backdrop")
            drawer.set_translucent(False)

    def _on_window_event(self, watched, event):
        """Keep the open drawer placed and above the panes."""
        event_type = event.type()

        if not self.drawer.isVisible():
            return False

        if event_type in _PLACING_EVENTS:
            self.place()

        # A pane added later (a plugin loaded at runtime) stacks above.
        elif event_type == QtCore.QEvent.Type.ChildAdded:
            self.drawer.raise_()

        return False

    def _on_window_input(self, watched, event):
        """Close the drawer on a press elsewhere in its window, using up the
        press and its release. Dialogs, menus and floating panes are other
        windows: their input never comes here."""
        event_type = event.type()
        releasing = event_type == QtCore.QEvent.Type.MouseButtonRelease

        if releasing and self._swallow_release:
            self._swallow_release = False

            if not self.model.is_open:
                self.stop()

            return True

        if event_type not in _PRESSES or not self.closes_on_click_outside:
            return False

        if not self.model.is_open or not self._is_outside(event.position()):
            return False

        self._swallow_release = True
        self.model.is_open = False

        return True

    def _is_outside(self, position):
        """Whether a press at ``position`` (window coordinates) is outside
        the drawer and every exempt widget."""
        point = position.toPoint()

        if self.drawer.geometry().contains(point):
            return False

        widget = self.window.childAt(point)

        if widget is None:
            return True

        return not any(
            widget is other or other.isAncestorOf(widget) for other in self.exempt
        )

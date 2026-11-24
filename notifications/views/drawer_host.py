# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications drawer on a main window, like a desktop notification
centre: anchored to the right, from below the menu bar and toolbars down to
the status bar, laid over the panes rather than moving them.

The host follows the model's ``is_open``. It builds the drawer's contents
the first time the drawer opens, keeps the drawer anchored as the window
resizes, and closes it on Esc or on a click elsewhere in the window. It is
no dock pane, so the task layout, presets and the View menu never see it.

The drawer's background behind the cards is faintly translucent while what
lies beneath is still; once that keeps repainting (a camera feed), the
drawer turns opaque until closed, so it is not repainted with every frame.
Nothing of this runs while the drawer is closed.

The model outlives any window: ``attach()`` puts the drawer on a window,
``detach()`` takes it off, and a window deleted without ``detach()`` is
let go of too.
"""

# Standard library imports.
import time
from collections import deque

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import (
    Any,
    Bool,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    observe,
)
from traitsui.api import UI

# Local imports.
from ..consts import (
    DRAWER_BACKDROP_PAINTS_PER_S,
    DRAWER_CLOSES_ON_CLICK_OUTSIDE,
    DRAWER_SLIDE_MS,
)
from ..models.notifications_pane_model import NotificationsPaneModel
from .drawer import NotificationsDrawer, anchored_drawer_rect

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Repaints within this many seconds of each other are one window repaint.
BACKDROP_SAME_FRAME_S = 0.015

#: Milliseconds after the drawer finishes sliding in during which repaints
#: are the drawer appearing, not what lies beneath changing.
BACKDROP_SETTLE_MS = 250

#: Presses that close the drawer when outside it.
_PRESS_EVENTS = (
    QtCore.QEvent.Type.MouseButtonPress,
    QtCore.QEvent.Type.MouseButtonDblClick,
)

#: Window events after which the open drawer is placed again.
_PLACING_EVENTS = (
    QtCore.QEvent.Type.Resize,
    QtCore.QEvent.Type.LayoutRequest,
    QtCore.QEvent.Type.Show,
)


class _EventRelay(QtCore.QObject):
    """An event filter handing every event to ``handler(watched, event)``."""

    def __init__(self, handler, parent=None):
        super().__init__(parent)

        self._handler = handler

    def eventFilter(self, watched, event):
        return self._handler(watched, event)


class NotificationsDrawerHost(HasTraits):
    """Puts a NotificationsDrawer on a QMainWindow and opens and closes it
    with the model."""

    #: Its ``is_open`` opens and closes the drawer.
    model = Instance(NotificationsPaneModel)

    #: Widgets whose clicks never count as outside the drawer: the bell,
    #: which toggles the drawer itself.
    click_outside_exempt = List()

    #: Whether a click elsewhere in the window closes the drawer.
    closes_on_click_outside = Bool(DRAWER_CLOSES_ON_CLICK_OUTSIDE)

    #: Duration (ms) of the slide in; 0 opens the drawer at once.
    slide_ms = Int(DRAWER_SLIDE_MS)

    #: The QMainWindow the drawer is on; None while detached.
    window = Any()

    #: The drawer widget; None while detached.
    drawer = Any()

    #: Whether the drawer's contents have been built (on first open).
    contents_built = Property(Bool, observe="_ui")

    #: The contents' TraitsUI UI once built.
    _ui = Instance(UI)

    #: Watches the window for resizes and new children.
    _window_relay = Any()

    #: Watches the whole application, while the drawer is open, for clicks
    #: and for repaints of what lies beneath a translucent drawer.
    _app_relay = Any()

    #: When what lies beneath repainted within the last second.
    _backdrop_paints = Instance(deque, ())

    #: Repaints before this time (time.monotonic()) are the drawer opening.
    _watch_backdrop_from = Float()

    #: Whether the release of a click that closed the drawer is still due.
    _swallow_release = Bool(False)

    #: The slide-in animation.
    _slide = Any()

    #: The widget that had the focus before the drawer took it.
    _focus_before = Any()

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def attach(self, window):
        """Put the drawer on ``window`` (a QMainWindow), closed unless the
        model is open."""
        self.detach()

        self.window = window
        self.drawer = drawer = NotificationsDrawer(window)
        drawer.hide()
        drawer.close_requested.connect(self._close_from_view)

        self._slide = QtCore.QPropertyAnimation(drawer, b"pos", drawer)
        self._slide.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)

        self._window_relay = _EventRelay(self._on_window_event, window)
        window.installEventFilter(self._window_relay)
        window.destroyed.connect(self._forget_window)

        if self.model.is_open:
            self._open()

    def detach(self):
        """Take the drawer off its window and close it. Safe to repeat."""

        if self.window is None:
            return

        window, drawer = self.window, self.drawer

        try:
            window.destroyed.disconnect(self._forget_window)
            window.removeEventFilter(self._window_relay)

        # The window is already gone; its children went with it.
        except RuntimeError as error:
            logger.debug(f"Notifications drawer window already deleted: {error}")

        self._remove_app_relay()
        self._dispose_contents()
        self._clear_references()

        try:
            drawer.deleteLater()

        except RuntimeError as error:
            logger.debug(f"Notifications drawer already deleted: {error}")

        self.model.is_open = False

    def _get_contents_built(self):
        return self._ui is not None

    # ------------------------------------------------------------------ #
    # Opening and closing                                                 #
    # ------------------------------------------------------------------ #

    @observe("model:is_open")
    def _follow_model(self, event):

        if self.drawer is None:
            return

        if event.new:
            self._open()

        else:
            self._close()

    def _open(self):
        drawer = self.drawer

        if self._ui is None:
            self._build_contents()

        final = self._place()
        drawer.show()
        drawer.raise_()

        if self.slide_ms > 0:
            self._slide.stop()
            self._slide.setDuration(self.slide_ms)
            self._slide.setStartValue(QtCore.QPoint(self.window.width(), final.y()))
            self._slide.setEndValue(final.topLeft())
            self._slide.start()

        self._focus_before = QtWidgets.QApplication.focusWidget()
        drawer.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)

        # Over a native window (a sibling made native) nothing composites
        # beneath a translucent widget.
        drawer.set_translucent(not drawer.internalWinId())
        self._backdrop_paints.clear()
        self._watch_backdrop_from = (
            time.monotonic() + (self.slide_ms + BACKDROP_SETTLE_MS) / 1000
        )

        if self.closes_on_click_outside or drawer.is_translucent():
            self._install_app_relay()

    def _close(self):
        drawer = self.drawer
        focus = QtWidgets.QApplication.focusWidget()
        had_focus = focus is not None and drawer.isAncestorOf(focus)

        self._slide.stop()
        drawer.hide()

        if not self._swallow_release:
            self._remove_app_relay()

        if had_focus or drawer.hasFocus():
            self._restore_focus()

    def _close_from_view(self):
        self.model.is_open = False

    def _restore_focus(self):
        """Give the focus back to where it was, if that widget still is."""
        widget, self._focus_before = self._focus_before, None

        try:
            if widget is not None and widget.isVisible():
                widget.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)

        # Deleted while the drawer was open.
        except RuntimeError as error:
            logger.debug(f"Focus target gone: {error}")

    def _build_contents(self):
        from .notification_list_editor import NotificationListView
        from .notifications_view import NotificationsView

        self._ui = self.model.edit_traits(
            view=NotificationsView, kind="subpanel", parent=self.drawer
        )
        contents = self._ui.control

        # The cards' list: what lies beneath shows between the cards.
        self.drawer.set_contents(
            contents, translucent_area=contents.findChild(NotificationListView)
        )

    def _dispose_contents(self):

        if self._ui is None:
            return

        # At app exit the window may already have deleted the contents.
        try:
            self._ui.dispose()

        except RuntimeError as error:
            logger.debug(f"Notifications drawer contents already deleted: {error}")

        self._ui = None

    # ------------------------------------------------------------------ #
    # Placement                                                           #
    # ------------------------------------------------------------------ #

    def _place(self):
        """Anchor the drawer to its window; return where it ends up."""
        rect = anchored_drawer_rect(self.window)

        # Mid-slide, only where the slide ends moves.
        if self._slide.state() == QtCore.QAbstractAnimation.State.Running:
            self._slide.setEndValue(rect.topLeft())
            self.drawer.resize(rect.size())

        else:
            self.drawer.setGeometry(rect)

        return rect

    # ------------------------------------------------------------------ #
    # Event filters                                                       #
    # ------------------------------------------------------------------ #

    def _on_window_event(self, watched, event):
        """Keep the open drawer anchored and above the panes."""
        drawer = self.drawer

        if drawer is None or not drawer.isVisible():
            return False

        event_type = event.type()

        if event_type in _PLACING_EVENTS:
            self._place()

        # A pane added later (a plugin loaded at runtime) stacks above.
        elif event_type == QtCore.QEvent.Type.ChildAdded:
            drawer.raise_()

        return False

    def _on_application_event(self, watched, event):
        """Close the drawer on a press elsewhere in its window, using up the
        press and its release; watch what lies beneath a translucent drawer
        for repaints."""
        event_type = event.type()

        if event_type == QtCore.QEvent.Type.Paint:
            self._note_backdrop_paint(watched, event)

            return False

        if event_type == QtCore.QEvent.Type.MouseButtonRelease:
            return self._end_swallowed_click(watched)

        if event_type not in _PRESS_EVENTS or not self.closes_on_click_outside:
            return False

        if not self._is_outside_drawer(watched):
            return False

        self._swallow_release = True
        self.model.is_open = False

        return True

    def _note_backdrop_paint(self, widget, event):
        """Turn the drawer opaque once what lies beneath keeps repainting: a
        translucent drawer is repainted with it, a camera feed's every frame.
        Repaints the drawer causes itself — sliding in, or under the mouse
        while used — do not count."""
        drawer = self.drawer

        if drawer is None or not drawer.is_translucent():
            return

        if not self._is_outside_drawer(widget, exempt=()):
            return

        now = time.monotonic()
        paints = self._backdrop_paints
        cursor = drawer.mapFromGlobal(QtGui.QCursor.pos())

        if now < self._watch_backdrop_from or drawer.rect().contains(cursor):
            return

        # One repaint of the window paints many widgets.
        if paints and now - paints[-1] < BACKDROP_SAME_FRAME_S:
            return

        painted = event.rect().translated(widget.mapTo(self.window, QtCore.QPoint()))

        if not painted.intersects(drawer.geometry()):
            return

        paints.append(now)

        while paints and now - paints[0] > 1.0:
            paints.popleft()

        if len(paints) > DRAWER_BACKDROP_PAINTS_PER_S:
            logger.debug("Notifications drawer turns opaque over a busy backdrop")
            drawer.set_translucent(False)

    def _end_swallowed_click(self, watched):

        if not self._swallow_release or not isinstance(watched, QtWidgets.QWidget):
            return False

        self._swallow_release = False

        if self.model is None or not self.model.is_open:
            self._remove_app_relay()

        return True

    def _is_outside_drawer(self, widget, exempt=None):
        """Whether ``widget`` is in the drawer's window but not the drawer,
        nor one of the ``exempt`` widgets (by default those exempt from
        closing it). Other windows (dialogs, menus, floating panes) never
        count."""
        drawer = self.drawer

        # Mouse events reach the window's QWindow before its widgets.
        if drawer is None or not isinstance(widget, QtWidgets.QWidget):
            return False

        if widget.window() is not self.window:
            return False

        if widget is drawer or drawer.isAncestorOf(widget):
            return False

        if exempt is None:
            exempt = self.click_outside_exempt

        return not any(
            widget is other or other.isAncestorOf(widget) for other in exempt
        )

    def _install_app_relay(self):

        if self._app_relay is None:
            self._app_relay = _EventRelay(self._on_application_event)
            QtWidgets.QApplication.instance().installEventFilter(self._app_relay)

    def _remove_app_relay(self):
        self._swallow_release = False

        if self._app_relay is not None:
            QtWidgets.QApplication.instance().removeEventFilter(self._app_relay)
            self._app_relay = None

    # ------------------------------------------------------------------ #
    # Window teardown                                                     #
    # ------------------------------------------------------------------ #

    def _forget_window(self, *args):
        """The window was deleted without ``detach()``: its children, the
        drawer and contents among them, went with it. The contents' UI is
        still disposed, so its editors stop listening to the model."""
        self._remove_app_relay()
        self._dispose_contents()
        self._clear_references()
        self.model.is_open = False

    def _clear_references(self):
        self.window = None
        self.drawer = None
        self._window_relay = None
        self._slide = None
        self._focus_before = None

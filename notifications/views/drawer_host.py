# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications drawer on a main window, like Windows 11's notification
centre: a floating panel at the bottom right, above the status bar by the
bell, as tall as its contents up to the window's room, laid over the panes
rather than moving them.

The host follows the model's ``is_open``. Nothing is built, and nothing
watches the window, until the drawer first opens: then the panel and its
contents are built, and while it is open the host keeps it placed, eases
its height to its contents, closes it on Esc or on a press elsewhere in the
window, and turns it opaque over a busy backdrop. It is no dock pane, so
the task layout, presets and the View menu never see it.

Where the drawer goes and what it shows are overridable: ``placement()``
and ``build_contents()``.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, Bool, HasTraits, Instance, Int, List, observe

# Microdrop style imports.
from microdrop_style.panel_metrics import DRAWER_SLIDE_MS

# Local imports.
from ..models.notifications_pane_model import NotificationsPaneModel
from .drawer import NotificationsDrawer, anchored_drawer_rect
from .drawer_watch import OpenDrawerWatch
from .view_consts import (
    DRAWER_CLOSES_ON_CLICK_OUTSIDE,
    DRAWER_FIT_MS,
    DRAWER_FIT_STEP_PX,
    DRAWER_INSET,
    DRAWER_MAX_WIDTH,
    DRAWER_MIN_HEIGHT,
    DRAWER_MIN_WIDTH,
    WINDOW_LEFT_IN_VIEW,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Milliseconds after the drawer finishes sliding in during which repaints
#: are the drawer appearing, not what lies beneath changing.
BACKDROP_SETTLE_MS = 250


def drawer_width_for(window_width, wanted):
    """The drawer's width in a ``window_width`` window, for ``wanted``."""
    widest = max(
        min(DRAWER_MAX_WIDTH, window_width - WINDOW_LEFT_IN_VIEW), DRAWER_MIN_WIDTH
    )

    return min(max(wanted, DRAWER_MIN_WIDTH), widest, window_width)


class NotificationsDrawerHost(HasTraits):
    """Puts a NotificationsDrawer on a QMainWindow and opens and closes it
    with the model."""

    #: Its ``is_open`` opens and closes the drawer; ``drawer_width`` sizes it.
    model = Instance(NotificationsPaneModel)

    #: Widgets whose presses never count as outside the drawer: the bell,
    #: which toggles the drawer itself.
    click_outside_exempt = List()

    #: Whether a press elsewhere in the window closes the drawer.
    closes_on_click_outside = Bool(DRAWER_CLOSES_ON_CLICK_OUTSIDE)

    #: Duration (ms) of the slide in; 0 opens the drawer at once.
    slide_ms = Int(DRAWER_SLIDE_MS)

    #: The QMainWindow the drawer is for; None while detached.
    window = Any()

    #: The drawer widget; None until first opened.
    drawer = Any()

    #: The built contents, whose ``natural_height()`` the drawer follows.
    _contents = Any()

    #: Whether the contents were built for another theme, and whether
    #: following a theme change is queued.
    _stale = Bool(False)
    _theme_queued = Bool(False)

    #: What the open drawer watches; made with the drawer.
    _watch = Instance(OpenDrawerWatch)

    #: The slide in, and the height following the contents.
    _slide = Any()
    _fit = Any()
    _height_target = Int(0)

    #: The widget that had the focus before the drawer took it.
    _focus_before = Any()

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def attach(self, window):
        """Put the drawer on ``window`` (a QMainWindow): closed and unbuilt
        unless the model is open."""
        self.detach()

        self.window = window
        window.destroyed.connect(self._forget_window)

        if self.model.is_open:
            self._open()

    def detach(self):
        """Take the drawer off its window and close it. Safe to repeat."""

        if self.window is None:
            return

        try:
            self.window.destroyed.disconnect(self._forget_window)

        # The window is already gone; its children went with it.
        except RuntimeError as error:
            logger.debug(f"Notifications drawer window already deleted: {error}")

        if self._watch is not None:
            self._watch.stop()

        self._dispose_contents()

        if self.drawer is not None:
            try:
                self.drawer.deleteLater()

            except RuntimeError as error:
                logger.debug(f"Notifications drawer already deleted: {error}")

        self._clear_references()
        self.model.is_open = False

    @property
    def contents_built(self):
        """Whether the drawer's contents have been built (on first open)."""
        return self._contents is not None

    def placement(self, available, natural_height):
        """Where the drawer goes within ``available`` (the window's room
        between its top bars and its status bar): at the right, inset, at
        the model's width, as tall as ``natural_height`` allows, its bottom
        by the status bar. Override to place it elsewhere."""
        width = drawer_width_for(available.width(), self.model.drawer_width)
        room = max(available.height() - 2 * DRAWER_INSET, 0)
        height = min(max(natural_height, DRAWER_MIN_HEIGHT), room)
        right = available.right() + 1 - DRAWER_INSET
        bottom = available.bottom() + 1 - DRAWER_INSET

        return QtCore.QRect(right - width, bottom - height, width, height)

    def build_contents(self, parent):
        """Build the drawer's contents in ``parent``. Returns the contents
        widget (with ``natural_height()``, a ``height_changed`` signal and
        ``dispose()``) and the widget behind which the panel is translucent.
        Opened by the app, the sections follow the header one per paced GUI
        turn. Override to show other contents."""
        from .column import DrawerContents

        contents = DrawerContents(self.model, parent)
        contents.follow_model_sections(paced=self.model.opened_by_app)

        return contents, contents.scroll

    # ------------------------------------------------------------------ #
    # Opening and closing                                                 #
    # ------------------------------------------------------------------ #

    @observe("model:is_open")
    def _follow_model(self, event):

        if self.window is None:
            return

        if event.new:
            self._open()

        elif self.drawer is not None:
            self._close()

    @observe("model:drawer_width")
    def _follow_width(self, event):

        if self.drawer is not None and self.drawer.isVisible():
            self._place()

    def _open(self):

        if self.drawer is None:
            self._build_drawer()

        if self._stale or self._contents is None:
            self._rebuild_contents()

        drawer = self.drawer
        final = self._place()
        drawer.show()
        drawer.raise_()

        if self.slide_ms > 0:
            self._slide.stop()
            self._slide.setDuration(self.slide_ms)
            self._slide.setStartValue(QtCore.QPoint(self.window.width(), final.y()))
            self._slide.setEndValue(final.topLeft())
            self._slide.start()

        # Opened by the app, the drawer leaves the focus to the window: Esc
        # reaches it from anywhere in the window instead.
        if not self.model.opened_by_app:
            self._focus_before = QtWidgets.QApplication.focusWidget()
            drawer.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)

        drawer.set_escape_window_wide(self.model.opened_by_app)

        # Over a native window (a sibling made native) nothing composites
        # beneath a translucent widget.
        drawer.set_translucent(not drawer.internalWinId())
        self._watch.closes_on_click_outside = self.closes_on_click_outside
        self._watch.start((self.slide_ms + BACKDROP_SETTLE_MS) / 1000)

    def _close(self):
        drawer = self.drawer
        focus = QtWidgets.QApplication.focusWidget()
        had_focus = focus is not None and drawer.isAncestorOf(focus)

        self._slide.stop()
        self._fit.stop()
        drawer.hide()
        drawer.set_escape_window_wide(False)

        self._watch.stop()

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

    # ------------------------------------------------------------------ #
    # Building                                                            #
    # ------------------------------------------------------------------ #

    def _build_drawer(self):
        self.drawer = drawer = NotificationsDrawer(self.window)
        drawer.hide()
        drawer.close_requested.connect(self._close_from_view)
        drawer.edge.width_requested.connect(self._resize_to)
        self._watch = OpenDrawerWatch(
            model=self.model,
            window=self.window,
            drawer=drawer,
            exempt=self.click_outside_exempt,
            place=self._place,
            busy=self._animating,
        )
        drawer.painted.connect(self._watch.note_paint)
        drawer.theme_changed.connect(self._queue_follow_theme)

        self._slide = QtCore.QPropertyAnimation(drawer, b"pos", drawer)
        self._slide.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)

        self._fit = QtCore.QVariantAnimation(drawer)
        self._fit.setDuration(DRAWER_FIT_MS)
        self._fit.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._fit.valueChanged.connect(self._set_height)

    def _rebuild_contents(self):
        """Build the contents afresh, every colour resolved for the current
        theme."""
        self._dispose_contents()
        self._stale = False
        self._contents, area = self.build_contents(self.drawer)

        self.drawer.set_contents(self._contents, translucent_area=area)
        self._contents.height_changed.connect(self._fit_height)

    def _dispose_contents(self):
        contents, self._contents = self._contents, None

        if contents is None:
            return

        # At app exit the window may already have deleted the contents.
        try:
            contents.dispose()
            contents.deleteLater()

        except RuntimeError as error:
            logger.debug(f"Notifications drawer contents already deleted: {error}")

    def _resize_to(self, width):
        self.model.drawer_width = drawer_width_for(self.window.width(), width)

    # ------------------------------------------------------------------ #
    # Placement                                                           #
    # ------------------------------------------------------------------ #

    def _natural_height(self, available):
        return (
            available.height()
            if self._contents is None
            else (self._contents.natural_height())
        )

    def _place(self):
        """Place the drawer where ``placement()`` says; return where it ends
        up."""
        available = anchored_drawer_rect(self.window)
        rect = self.placement(available, self._natural_height(available))

        self._fit.stop()
        self._height_target = rect.height()

        # Mid-slide, only where the slide ends moves.
        if self._slide.state() == QtCore.QAbstractAnimation.State.Running:
            self._slide.setEndValue(rect.topLeft())
            self.drawer.resize(rect.size())

        else:
            self.drawer.setGeometry(rect)

        return rect

    def _fit_height(self):
        """Ease the top edge to the contents' new height: at once for small
        steps (a section folding frame by frame), not at all for a pixel or
        two, never during the slide."""
        drawer = self.drawer

        if drawer is None or not drawer.isVisible() or self._contents is None:
            return

        if self._slide.state() == QtCore.QAbstractAnimation.State.Running:
            self._place()

            return

        available = anchored_drawer_rect(self.window)
        target = self.placement(available, self._natural_height(available)).height()

        if abs(target - self._height_target) < 2:
            return

        self._height_target = target
        current = drawer.height()
        self._fit.stop()

        if abs(target - current) < DRAWER_FIT_STEP_PX:
            self._set_height(target)

            return

        self._fit.setStartValue(current)
        self._fit.setEndValue(target)
        self._fit.start()

    def _animating(self):
        """Whether the drawer is sliding in or easing its height."""
        running = QtCore.QAbstractAnimation.State.Running

        return running in (self._slide.state(), self._fit.state())

    def _set_height(self, height):
        available = anchored_drawer_rect(self.window)
        rect = self.placement(available, int(height))

        self.drawer.setGeometry(rect)

    # ------------------------------------------------------------------ #
    # Theme and teardown                                                  #
    # ------------------------------------------------------------------ #

    def _queue_follow_theme(self):
        """Follow the theme once the switch has settled: every widget hears
        of it, one after another."""

        if not self._theme_queued:
            self._theme_queued = True
            QtCore.QTimer.singleShot(0, self.follow_theme)

    def follow_theme(self):
        """The theme changed: rebuild the contents, so no part keeps the
        other theme's colours; while closed, at the next opening."""
        self._theme_queued = False

        if self._contents is None:
            return

        if self.drawer is not None and self.drawer.isVisible():
            self._rebuild_contents()
            self._place()

        else:
            self._stale = True

    def _forget_window(self, *args):
        """The window was deleted without ``detach()``: its children, the
        drawer and contents among them, went with it. The contents' UI is
        still disposed, so its editors stop listening to the model."""
        self._dispose_contents()
        self._clear_references()
        self.model.is_open = False

    def _clear_references(self):
        self.window = None
        self.drawer = None
        self._watch = None
        self._slide = None
        self._fit = None
        self._focus_before = None

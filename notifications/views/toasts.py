# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Toasts: new notifications pop up as cards at the bottom right of the main
window, just above the status bar by the bell, newest at the bottom. They
slide in from the right edge; leaving, they fly into the bell (still unread)
or fade away (acted on). Past the limit a "+N more" pill sits above them.

The view follows the pane model's toasts and reports clicks to the toast
controller and the pane model; it never decides when a toast comes or goes.
Nothing is built, and the window is not watched, until a toast shows.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, Dict, HasTraits, Instance, observe

# Local imports.
from ..controllers.toast_controller import ToastStackController
from ..models.notifications_pane_model import NotificationsPaneModel
from .toast_widgets import SHADOW, MorePill, ToastGhost, ToastWidget, lerp_rect
from .view_consts import (
    TOAST_ENTER_MS,
    TOAST_FLY_MS,
    TOAST_GAP,
    TOAST_MARGIN,
    TOAST_RESTACK_MS,
    TOAST_WIDTH,
)

#: Size (px) a toast shrinks to as it reaches the bell, and its opacity there.
LANDED_SIZE = 18
LANDED_OPACITY = 0.25

_DIRECT_CHILDREN = QtCore.Qt.FindChildOption.FindDirectChildrenOnly

_RESTACKING_EVENTS = (
    QtCore.QEvent.Type.Resize,
    QtCore.QEvent.Type.LayoutRequest,
    QtCore.QEvent.Type.Show,
)


class _WindowRelay(QtCore.QObject):
    """Hands the window's events to ``handler(event)``."""

    def __init__(self, handler, parent):
        super().__init__(parent)

        self._handler = handler

    def eventFilter(self, watched, event):
        self._handler(event)

        return False


class ToastStackView(HasTraits):
    """Shows the model's toasts on a QMainWindow."""

    #: The toasts, the notifications and whether the drawer is open.
    pane_model = Instance(NotificationsPaneModel)

    #: Told when a toast is dismissed.
    controller = Instance(ToastStackController)

    #: Where toasts fly to: the bell icon (a NotificationBellIcon).
    bell = Any()

    #: The QMainWindow; None while detached.
    window = Any()

    #: Each toast item's widget.
    _widgets = Dict()

    #: Running animations, held until they finish.
    _animations = Dict()

    #: The "+N more" pill; made with the first toast.
    _more = Any()

    #: Watches the window for resizes and new children while toasts show.
    _relay = Any()

    # ------------------------------------------------------------------ #
    # Window                                                              #
    # ------------------------------------------------------------------ #

    def attach(self, window):
        """Show the toasts on ``window`` from now on."""
        self.detach()

        self.window = window
        window.destroyed.connect(self._forget_window)
        self._sync(animate=False)

    def detach(self):
        """Take the toasts off their window."""

        if self.window is None:
            return

        try:
            self.window.destroyed.disconnect(self._forget_window)
            self._unwatch()

            for widget in self._widgets.values():
                widget.card.dispose()
                widget.deleteLater()

            if self._more is not None:
                self._more.deleteLater()

        # The window is already gone; its children went with it.
        except RuntimeError:
            pass

        self._forget_window()

    def _forget_window(self, *args):
        self.window = None
        self._widgets = {}
        self._animations = {}
        self._more = None
        self._relay = None

    def _watch(self):

        if self._relay is None:
            self._relay = _WindowRelay(self._on_window_event, self.window)
            self.window.installEventFilter(self._relay)

    def _unwatch(self):

        if self._relay is not None:
            self.window.removeEventFilter(self._relay)
            self._relay = None

    def _on_window_event(self, event):
        event_type = event.type()

        if event_type in _RESTACKING_EVENTS:
            self._restack(animate=False)

        elif event_type == QtCore.QEvent.Type.ChildAdded:
            self._raise_all()

    def _reveal_overflow(self):
        """Open the drawer on the newest toast that did not fit: the others
        are listed right under it."""
        overflow = self.pane_model.toasts.overflow_entries

        if overflow:
            self.pane_model.reveal_entry(overflow[-1])

        else:
            self.pane_model.is_open = True

    # ------------------------------------------------------------------ #
    # Following the model                                                 #
    # ------------------------------------------------------------------ #

    @observe("pane_model:toasts:items.items")
    def _items_changed(self, event):
        self._sync(animate=True)

    @observe("pane_model:toasts:items:items:leaving")
    def _leave(self, event):

        if event.object.leaving:
            self._fly_away(event.object)
            self._restack(animate=True)

    @observe("pane_model:toasts:items:items:remaining_ms")
    def _show_countdown(self, event):
        widget = self._widgets.get(event.object)

        if widget is not None:
            widget.card.set_progress(self.pane_model.toasts.progress(event.object))

    @observe("pane_model:toasts:settings:[auto_dismiss, auto_dismiss_seconds]")
    def _show_all_countdowns(self, event):
        """The countdowns follow a change of the settings at once."""

        for item, widget in self._widgets.items():
            widget.card.set_progress(self.pane_model.toasts.progress(item))

    @observe("pane_model:toasts:overflow")
    def _show_overflow(self, event):
        self._restack(animate=True)

    def _sync(self, animate):
        """Make a widget for each new toast, drop those of removed ones."""

        if self.window is None:
            return

        items = self.pane_model.toasts.items

        for item in [item for item in self._widgets if item not in items]:
            widget = self._widgets.pop(item)
            widget.card.dispose()
            widget.deleteLater()

        for item in items:
            if item not in self._widgets and not item.leaving:
                self._widgets[item] = self._make_widget(item)

        if items:
            self._watch()

        else:
            self._unwatch()

        self._restack(animate)

    def _make_widget(self, item):
        model = self.pane_model
        widget = ToastWidget(item.entry, self.window, model.help_available)
        card = widget.card

        card.set_progress(model.toasts.progress(item))
        card.dismiss_clicked.connect(lambda entry: self.controller.dismiss(item))
        card.action_clicked.connect(lambda entry: setattr(model, "run_action", entry))
        card.secondary_clicked.connect(
            lambda entry: setattr(model, "run_secondary_action", entry)
        )
        card.body_clicked.connect(model.reveal_entry)
        card.link_clicked.connect(lambda entry, path: self._open_link(path))
        widget.hover_changed.connect(self._pause_all)

        return widget

    def _open_link(self, path):
        """Open a detail link's folder, as a drawer card's link does. The
        file manager can come up over the toast without the toast seeing
        the pointer leave, so the countdowns run on rather than stay held."""
        self.pane_model.open_link = path
        self._pause_all(False)

    def _pause_all(self, hovered):
        """Hovering any toast holds them all: the stack is being read."""

        for item in self.pane_model.toasts.items:
            item.hovered = hovered

    # ------------------------------------------------------------------ #
    # Layout                                                              #
    # ------------------------------------------------------------------ #

    def _bottom(self):
        window = self.window
        status_bar = window.findChild(QtWidgets.QStatusBar, options=_DIRECT_CHILDREN)

        if status_bar is not None and status_bar.isVisible():
            return status_bar.geometry().top() - TOAST_MARGIN + SHADOW - 4

        return window.height() - TOAST_MARGIN

    def _restack(self, animate):
        """Stack the staying toasts up from the bottom, newest lowest."""

        if self.window is None:
            return

        window = self.window
        card_width = min(TOAST_WIDTH, window.width() - 2 * TOAST_MARGIN)
        left = window.width() - TOAST_MARGIN - card_width - SHADOW
        bottom = self._bottom()

        for item in reversed(self.pane_model.toasts.items):
            widget = self._widgets.get(item)

            if widget is None or item.leaving:
                continue

            height = widget.height_for(card_width)
            target = QtCore.QPoint(left, bottom - height)
            fresh = not widget.isVisible()

            widget.resize(card_width + 2 * SHADOW, height)

            if fresh:
                widget.move(window.width(), target.y())
                widget.show()
                widget.raise_()

            if animate:
                duration = TOAST_ENTER_MS if fresh else TOAST_RESTACK_MS
                self._animate_to(widget, target, duration)

            else:
                widget.move(target)

            bottom = target.y() + SHADOW - 4 - TOAST_GAP

        self._place_more(left + SHADOW, card_width, bottom)

    def _place_more(self, card_left, card_width, bottom):
        overflow = self.pane_model.toasts.overflow

        if not overflow or self.pane_model.is_open:
            if self._more is not None:
                self._more.hide()

            return

        if self._more is None:
            self._more = MorePill(self.window)
            self._more.clicked.connect(self._reveal_overflow)

        self._more.setText(f"+{overflow} more in notifications")
        self._more.adjustSize()
        size = self._more.sizeHint()
        self._more.setGeometry(
            card_left + card_width - size.width(),
            bottom - size.height(),
            size.width(),
            size.height(),
        )
        self._more.show()
        self._more.raise_()

    def _animate_to(self, widget, target, duration):
        running = self._animations.get(widget)

        if running is not None:
            running.stop()

        animation = QtCore.QPropertyAnimation(widget, b"pos", widget)
        animation.setDuration(duration)
        animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        animation.setEndValue(target)
        animation.start()
        self._animations[widget] = animation

    def _raise_all(self):

        for widget in self._widgets.values():
            widget.raise_()

        if self._more is not None:
            self._more.raise_()

    # ------------------------------------------------------------------ #
    # Leaving                                                             #
    # ------------------------------------------------------------------ #

    def _fly_away(self, item):
        """Hide the toast and animate a picture of it into the bell (or just
        away), then take it off the model."""
        widget = self._widgets.get(item)
        window = self.window

        if widget is None or window is None or not widget.isVisible():
            self.pane_model.toasts.remove(item)

            return

        card = widget.card
        start = QtCore.QRect(card.mapTo(window, QtCore.QPoint(0, 0)), card.size())
        ghost = ToastGhost(card.grab(), window)
        ghost.setGeometry(start)
        ghost.show()
        ghost.raise_()
        widget.hide()

        end, end_opacity = self._landing(start, item.into_bell)
        animation = QtCore.QVariantAnimation(ghost)
        animation.setDuration(TOAST_FLY_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(
            QtCore.QEasingCurve.Type.InOutCubic
            if item.into_bell
            else QtCore.QEasingCurve.Type.OutCubic
        )

        def step(value):
            ghost.setGeometry(lerp_rect(start, end, value))
            ghost.opacity = 1 + (end_opacity - 1) * value
            ghost.update()

        def done():
            ghost.deleteLater()
            self.pane_model.toasts.remove(item)

        animation.valueChanged.connect(step)
        animation.finished.connect(done)
        animation.start()

    def _landing(self, start, into_bell):
        """Where a leaving toast ends, and its opacity there."""
        bell = self.bell

        if into_bell and bell is not None and bell.isVisible():
            center = bell.mapTo(self.window, bell.bell_center())
            end = QtCore.QRect(0, 0, LANDED_SIZE, LANDED_SIZE // 2)
            end.moveCenter(center)

            return end, LANDED_OPACITY

        return start.translated(start.width() + 2 * TOAST_MARGIN, 0), 0.0

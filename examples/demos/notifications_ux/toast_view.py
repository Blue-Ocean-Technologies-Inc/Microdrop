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

The view follows a ToastStackModel and reports clicks to the controller and
the pane model; it never decides when a toast comes or goes.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Dict, HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR

# Local imports.
from .card_view import NotificationCard
from .typography import CHIP, role_font
from .ux_consts import (
    TOAST_ENTER_MS,
    TOAST_FLY_MS,
    TOAST_GAP,
    TOAST_MARGIN,
    TOAST_RESTACK_MS,
    TOAST_WIDTH,
)
from .ux_controllers import ToastStackController
from .ux_models import UxPaneModel
from .view_styles import card_border, card_fill, css, readable_accent

#: Room (px) around a toast's card for its shadow.
SHADOW = 12

#: Opacity of the shadow right under the card.
SHADOW_ALPHA = 0.10

#: Size (px) a toast shrinks to as it reaches the bell, and its opacity there.
LANDED_SIZE = 18
LANDED_OPACITY = 0.25

_DIRECT_CHILDREN = QtCore.Qt.FindChildOption.FindDirectChildrenOnly

_RESTACKING_EVENTS = (
    QtCore.QEvent.Type.Resize,
    QtCore.QEvent.Type.LayoutRequest,
    QtCore.QEvent.Type.Show,
)


class ToastWidget(QtWidgets.QWidget):
    """A toast card on a soft shadow; reports the pointer over it."""

    hover_changed = QtCore.Signal(bool)

    def __init__(self, entry, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(SHADOW, SHADOW - 4, SHADOW, SHADOW + 4)

        self.card = NotificationCard(entry, self, toast=True)
        layout.addWidget(self.card)

    def height_for(self, card_width):
        """The toast's height with a ``card_width`` card."""
        width = card_width + 2 * SHADOW
        height = self.heightForWidth(width)

        return height if height > 0 else self.sizeHint().height()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        card = QtCore.QRectF(self.card.geometry())

        for step in range(SHADOW, 0, -2):
            alpha = SHADOW_ALPHA * (1 - step / SHADOW) ** 2
            painter.setBrush(QtGui.QColor(0, 0, 0, int(alpha * 255)))
            painter.drawRoundedRect(
                card.adjusted(-step, -step + 3, step, step + 3), 8 + step, 8 + step
            )

    def enterEvent(self, event):
        self.hover_changed.emit(True)

        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_changed.emit(False)

        super().leaveEvent(event)


class _Ghost(QtWidgets.QWidget):
    """A picture of a leaving toast, drawn into its animated rectangle."""

    def __init__(self, pixmap, parent):
        super().__init__(parent)

        self.pixmap = pixmap
        self.opacity = 1.0

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self.opacity)
        painter.drawPixmap(self.rect(), self.pixmap)


class _MorePill(QtWidgets.QPushButton):
    """ "+N more in notifications", above the toasts. Its style sheet sets
    its own palette, so it restyles from the application's."""

    def restyle(self):
        palette = QtWidgets.QApplication.palette()

        self.setFont(role_font(CHIP))
        self.setStyleSheet(
            "QPushButton {"
            f" background: {css(card_fill(palette))};"
            f" color: {css(readable_accent(INFO_COLOR, palette))};"
            f" border: 1px solid {css(card_border(palette))};"
            " border-radius: 13px; padding: 4px 14px; }"
            f" QPushButton:hover {{ background: {css(card_fill(palette, True))}; }}"
        )

    def event(self, event):

        if event.type() == QtCore.QEvent.Type.ApplicationPaletteChange:
            self.restyle()

        return super().event(event)


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
    pane_model = Instance(UxPaneModel)

    #: Told when a toast is dismissed.
    controller = Instance(ToastStackController)

    #: Where toasts fly to: the bell icon (a UxBellIcon).
    bell = Any()

    #: The QMainWindow; None while detached.
    window = Any()

    #: Each toast item's widget.
    _widgets = Dict()

    #: Running animations, held until they finish.
    _animations = Dict()

    #: The "+N more" pill.
    _more = Any()

    #: Watches the window for resizes and new children.
    _relay = Any()

    # ------------------------------------------------------------------ #
    # Window                                                              #
    # ------------------------------------------------------------------ #

    def attach(self, window):
        """Show the toasts on ``window``."""
        self.window = window
        self._relay = _WindowRelay(self._on_window_event, window)
        window.installEventFilter(self._relay)
        window.destroyed.connect(self._forget_window)

        self._more = _MorePill(window)
        self._more.restyle()
        self._more.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._more.setToolTip("These went straight to the bell. Click to see them.")
        self._more.clicked.connect(self._reveal_overflow)
        self._more.hide()

        self._sync(animate=False)

    def _forget_window(self, *args):
        self.window = None
        self._widgets = {}
        self._animations = {}
        self._more = None

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
        item = event.object

        if item.leaving:
            self._fly_away(item)
            self._restack(animate=True)

    @observe("pane_model:toasts:items:items:remaining_ms")
    def _show_countdown(self, event):
        widget = self._widgets.get(event.object)

        if widget is not None:
            widget.card.set_progress(self._progress(event.object))

    @observe("pane_model:toasts:settings:[auto_dismiss, auto_dismiss_seconds]")
    def _show_all_countdowns(self, event):
        """The countdowns follow a change of the settings at once."""

        for item, widget in self._widgets.items():
            widget.card.set_progress(self._progress(item))

    @observe("pane_model:toasts:overflow")
    def _show_overflow(self, event):
        self._restack(animate=True)

    def _progress(self, item):
        return self.pane_model.toasts.progress(item)

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

        self._restack(animate)

    def _make_widget(self, item):
        widget = ToastWidget(item.entry, self.window)
        card = widget.card
        model = self.pane_model

        card.set_progress(self._progress(item))
        card.dismiss_clicked.connect(lambda entry: self.controller.dismiss(item))
        card.action_clicked.connect(lambda entry: setattr(model, "run_action", entry))
        card.secondary_clicked.connect(
            lambda entry: setattr(model, "run_secondary_action", entry)
        )
        card.body_clicked.connect(model.reveal_entry)
        widget.hover_changed.connect(self._pause_all)

        return widget

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
                self._animate_to(
                    widget, target, TOAST_ENTER_MS if fresh else TOAST_RESTACK_MS
                )

            else:
                widget.move(target)

            bottom = target.y() + SHADOW - 4 - TOAST_GAP

        self._place_more(left + SHADOW, card_width, bottom)

    def _place_more(self, card_left, card_width, bottom):
        overflow = self.pane_model.toasts.overflow

        if not overflow or self.pane_model.is_open:
            self._more.hide()

            return

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
        """Hide the toast and animate a picture of it into the bell (or
        just away), then take it off the model."""
        widget = self._widgets.get(item)
        window = self.window

        if widget is None or window is None or not widget.isVisible():
            self.pane_model.toasts.remove(item)

            return

        card = widget.card
        start = QtCore.QRect(card.mapTo(window, QtCore.QPoint(0, 0)), card.size())
        ghost = _Ghost(card.grab(), window)
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
            ghost.setGeometry(_lerp_rect(start, end, value))
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


def _lerp_rect(start, end, amount):
    """The rectangle ``amount`` (0-1) of the way from ``start`` to ``end``."""

    def lerp(first, second):
        return int(round(first + (second - first) * amount))

    return QtCore.QRect(
        lerp(start.x(), end.x()),
        lerp(start.y(), end.y()),
        max(lerp(start.width(), end.width()), 1),
        max(lerp(start.height(), end.height()), 1),
    )

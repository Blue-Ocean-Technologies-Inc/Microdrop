# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Help mode: explore the app by touch.

While it is on, touching a control does not operate it: a help bubble
describes it and an accent outline marks it, and sliding the finger moves
both live to whatever is under it. Every press, release, drag, key,
wheel, context menu and flick is swallowed, except on the Help-mode
controls themselves; Esc, Done or the toggle end it.
"""

# Enthought library imports.
from pyface.qt.QtCore import QEvent, QObject, Qt, QTimer
from pyface.qt.QtWidgets import QApplication, QScroller
from traits.api import Any, Bool, HasTraits, Instance, List, observe

# Local imports.
from .consts import (
    HELP_MODE_CONTROL_PROPERTY,
    HELP_TRANSIENT_HIDE_MS,
    SUSPENDED_SCROLLER_PROPERTY,
)
from .help_bubble import HelpBubble
from .help_overlay import HelpBanner, HelpOutline
from .help_resolver import resolve_help

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Events Help mode swallows (on everything but its own controls).
_SWALLOWED_EVENTS = frozenset(
    (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseMove,
        QEvent.Type.TouchBegin,
        QEvent.Type.TouchUpdate,
        QEvent.Type.TouchEnd,
        QEvent.Type.Wheel,
        QEvent.Type.ContextMenu,
        QEvent.Type.KeyPress,
        QEvent.Type.KeyRelease,
        QEvent.Type.ShortcutOverride,
        QEvent.Type.ToolTip,
    )
)

#: Of those, the ones that point at something to describe.
_POINTING_EVENTS = frozenset(
    (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseMove,
        QEvent.Type.TouchBegin,
        QEvent.Type.TouchUpdate,
    )
)


def is_help_mode_control(widget):
    """Whether ``widget`` is (inside) a Help-mode control, which keeps
    working while Help mode is on."""

    while widget is not None:
        if widget.property(HELP_MODE_CONTROL_PROPERTY):
            return True

        widget = widget.parentWidget()

    return False


def pointed_position(event):
    """The global point a pointing event aims at, or None (a mouse move
    with no button down is hover, not pointing)."""

    if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate):
        points = event.points()

        return points[0].globalPosition().toPoint() if points else None

    if (
        event.type() == QEvent.Type.MouseMove
        and event.buttons() == Qt.MouseButton.NoButton
    ):
        return None

    return event.globalPosition().toPoint()


class HelpPresenter(QObject):
    """Shows the help bubble and outline for what is at a point."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bubble = HelpBubble()
        self._outline = HelpOutline()
        self._topic = None

        #: Hides a long-press bubble shown outside Help mode.
        self._transient_timer = QTimer(self)
        self._transient_timer.setSingleShot(True)
        self._transient_timer.setInterval(HELP_TRANSIENT_HIDE_MS)
        self._transient_timer.timeout.connect(self.hide)

    def present(self, global_point, window=None, ignored_windows=(), outline=True):
        """Describe what is at ``global_point`` in ``window`` (default: the
        topmost window there); an unchanged topic only stays where it is."""
        topic = resolve_help(global_point, window, (self.bubble, *ignored_windows))

        if topic is None or topic.same_as(self._topic):
            return

        self._topic = topic
        self.bubble.show_topic(topic, global_point)

        if outline:
            self._outline.outline(topic.widget.window(), topic.anchor)

    def present_transient(self, global_point, _text=""):
        """The long-press tooltip fallback outside Help mode: the bubble for
        what is at ``global_point``, gone after a while or at the next
        press."""
        self._topic = None
        self.present(global_point, outline=False)
        self._transient_timer.start()
        QApplication.instance().installEventFilter(self)

    def hide(self):
        QApplication.instance().removeEventFilter(self)
        self._transient_timer.stop()
        self._topic = None
        self.bubble.hide()
        self._outline.hide()

    def eventFilter(self, watched, event):
        """Installed only while a long-press bubble is up: the next press
        anywhere puts it away."""

        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.TouchBegin):
            self.hide()

        return False


class HelpModeFilter(QObject):
    """The application event filter installed while Help mode is on."""

    def __init__(self, presenter, banner, exit_help_mode, parent=None):
        super().__init__(parent)
        self._presenter = presenter
        self._banner = banner
        self._exit_help_mode = exit_help_mode

    def eventFilter(self, watched, event):
        event_type = event.type()

        # Mouse and touch input reach the QWindow first; it hands them to
        # the widget, where they are swallowed.
        if event_type not in _SWALLOWED_EVENTS or not watched.isWidgetType():
            return False

        if watched.window() is self._banner or is_help_mode_control(watched):
            return False

        if event_type == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._exit_help_mode()

        elif event_type in _POINTING_EVENTS:
            global_point = pointed_position(event)

            if global_point is not None:
                # Resolved in the window the touch landed in, by position:
                # disabled controls never receive it.
                self._presenter.present(global_point, watched.window(), (self._banner,))

        # Accepted, so Qt neither replays a touch as a mouse event nor runs
        # the shortcut the key would trigger.
        event.accept()

        return True


class HelpModeController(HasTraits):
    """Turns Help mode on and off; one for the app (help_mode_controller)."""

    #: Whether Help mode is on.
    active = Bool(False)

    #: The bubble and outline, shared with the long-press help fallback.
    presenter = Instance(HelpPresenter)

    #: The toggle buttons on screen, kept checked in step with ``active``.
    _toggle_buttons = List()

    #: The banner and the event filter, while Help mode is on.
    _banner = Instance(HelpBanner)
    _filter = Any()

    def _presenter_default(self):
        return HelpPresenter()

    def register_toggle_button(self, button):
        """Keep ``button`` (a checkable Help-mode toggle) in step."""
        button.setProperty(HELP_MODE_CONTROL_PROPERTY, True)
        button.setChecked(self.active)
        button.toggled.connect(self._toggled_from_button)
        button.destroyed.connect(lambda *_: self._forget_toggle_button(button))
        self._toggle_buttons.append(button)

    def _forget_toggle_button(self, button):
        if button in self._toggle_buttons:
            self._toggle_buttons.remove(button)

    def _toggled_from_button(self, checked):
        self.active = checked

    @observe("active")
    def _apply_active(self, event):
        for button in self._toggle_buttons:
            button.setChecked(self.active)

        app = QApplication.instance()

        if self.active:
            window = app.activeWindow()
            self._banner = HelpBanner(window)
            self._banner.done.connect(self._end)
            self._banner.show_over(window)

            self._filter = HelpModeFilter(self.presenter, self._banner, self._end)
            app.installEventFilter(self._filter)
            suspend_flick_scrolling()

        else:
            app.removeEventFilter(self._filter)
            self._filter = None
            self._banner.close()
            self._banner.deleteLater()
            self._banner = None
            self.presenter.hide()
            resume_flick_scrolling()

        logger.info(f"Help mode {'on' if self.active else 'off'}")

    def _end(self):
        self.active = False


def suspend_flick_scrolling():
    """Ungrab every flick-scrolling gesture: QScroller sees touches before
    any event filter, so it would scroll under a finger exploring help."""

    for widget in QApplication.allWidgets():
        if QScroller.hasScroller(widget) and QScroller.grabbedGesture(widget).value:
            QScroller.ungrabGesture(widget)
            widget.setProperty(SUSPENDED_SCROLLER_PROPERTY, True)


def resume_flick_scrolling():
    """Grab again what suspend_flick_scrolling ungrabbed; the app only ever
    grabs touch flick gestures."""

    for widget in QApplication.allWidgets():
        if widget.property(SUSPENDED_SCROLLER_PROPERTY):
            QScroller.grabGesture(widget, QScroller.ScrollerGestureType.TouchGesture)
            widget.setProperty(SUSPENDED_SCROLLER_PROPERTY, None)


#: The one Help-mode controller the toggles and menu actions talk to.
help_mode_controller = HelpModeController()

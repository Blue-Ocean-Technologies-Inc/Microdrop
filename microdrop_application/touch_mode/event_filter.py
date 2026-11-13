# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The application-level event filter behind Touch mode.

One hook for every widget, so no call site changes: numeric spin boxes open
the number pad when their value is tapped (and an item-view cell editor
opens it straight away), steppers centre their value and accelerate on a
held button, scroll areas shown later get flick scrolling, and a tapped
text field brings up the Touch Assist keyboard. Everything it changes on a
widget is marked, so uninstalling restores it.
"""

# Enthought library imports.
from pyface.qt.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from pyface.qt.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QGraphicsView,
    QHeaderView,
    QLineEdit,
    QPlainTextEdit,
    QScroller,
    QTextEdit,
)

# Microdrop style imports.
from microdrop_style.touch_style import (
    TOUCH_COMPACT_PROPERTY,
    TOUCH_FRAME_PX,
    TOUCH_TARGET_PX,
)

# Local imports.
from ..touch_assist.consts import TOOL_KEYBOARD
from ..touch_assist.manager import touch_assist_manager
from .consts import (
    ADAPTED_ACCELERATION_PROPERTY,
    ADAPTED_ALIGNMENT_PROPERTY,
    ADAPTED_MAX_HEIGHT_PROPERTY,
    ADAPTED_MIN_WIDTH_PROPERTY,
    FLICK_SCROLLING_PROPERTY,
    PAD_OPENED_PROPERTY,
)
from .spin_box_session import (
    NUMERIC_SPIN_BOXES,
    SpinBoxPadSession,
    is_delegate_editor,
    item_view_cell,
)
from .touch_fit import clear_touch_fit, mark_touch_fit, thin_scroll_bars

#: The only event types the filter acts on; everything else passes at once.
_WATCHED_EVENTS = frozenset(
    (
        QEvent.Type.Polish,
        QEvent.Type.Show,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseButtonRelease,
    )
)

#: Spin-box values sit centred between the stepper's minus and plus.
_STEPPER_ALIGNMENT = Qt.AlignmentFlag.AlignCenter


def editable_numeric_spin_box(widget):
    """Return the numeric spin box ``widget`` is the line edit of, when it
    is enabled and editable; else None."""
    spin_box = widget.parentWidget()

    if (
        not isinstance(spin_box, NUMERIC_SPIN_BOXES)
        or spin_box.lineEdit() is not widget
    ):
        return None

    if not spin_box.isEnabled() or spin_box.isReadOnly():
        return None

    return spin_box


def editable_text_field(widget):
    """Return the plain text field ``widget`` is (or is the viewport of),
    when it is editable: not read-only and not a spin box's line edit."""
    field = widget

    if isinstance(widget.parentWidget(), (QTextEdit, QPlainTextEdit)):
        field = widget.parentWidget()

    if isinstance(field, QLineEdit):
        if isinstance(field.parentWidget(), QAbstractSpinBox):
            return None

        return None if field.isReadOnly() else field

    if isinstance(field, (QTextEdit, QPlainTextEdit)):
        return None if field.isReadOnly() else field

    return None


class TouchModeEventFilter(QObject):
    """Install on the QApplication with ``install``; ``uninstall`` undoes it."""

    def __init__(self, parent=None):
        super().__init__(parent)

        #: The spin-box line edit the current press landed on.
        self._pressed_line_edit = None

        #: Whether the keyboard on screen is one this filter brought up.
        self._keyboard_shown = False

    def install(self):
        """Filter every event, and mark the widgets already on screen for
        the touch style; ``adapt_existing`` finishes them once it applies."""
        app = QApplication.instance()
        app.installEventFilter(self)
        app.focusChanged.connect(self._on_focus_changed)

        for widget in QApplication.allWidgets():
            mark_touch_fit(widget)

    def adapt_existing(self):
        """Adapt the widgets already on screen, sized by the touch style."""

        for widget in QApplication.allWidgets():
            self._adapt(widget)

    def uninstall(self):
        """Stop filtering, and undo every adaptation."""
        app = QApplication.instance()
        app.removeEventFilter(self)
        app.focusChanged.disconnect(self._on_focus_changed)

        for widget in QApplication.allWidgets():
            self._restore(widget)

        if self._keyboard_shown:
            touch_assist_manager.set_visible(TOOL_KEYBOARD, False)
            self._keyboard_shown = False

    def eventFilter(self, watched, event):
        event_type = event.type()

        if event_type not in _WATCHED_EVENTS or not watched.isWidgetType():
            return False

        # Polish reaches the filter before the style polishes the widget, so
        # the compact mark is in place when the stylesheet is matched.
        if event_type == QEvent.Type.Polish:
            mark_touch_fit(watched)

            return False

        if event_type == QEvent.Type.Show:
            self._adapt(watched)
            self._open_pad_for_cell_editor(watched)

            return False

        if event.button() != Qt.MouseButton.LeftButton:
            return False

        if event_type == QEvent.Type.MouseButtonRelease:
            return self._on_release(watched, event)

        if editable_numeric_spin_box(watched) is None:
            return False

        # Swallowed, focus included: no text cursor or selection starts, and
        # the spin box does not emit a stray editingFinished as the pad takes
        # focus from it.
        self._pressed_line_edit = watched

        return True

    #### Spin boxes ###########################################################

    def _on_release(self, watched, event):
        pressed_line_edit = self._pressed_line_edit
        self._pressed_line_edit = None

        if watched is not pressed_line_edit:
            # Only a finger brings up the on-screen keyboard; a mouse user
            # has a physical one.
            if event.source() != Qt.MouseEventSource.MouseEventNotSynthesized:
                self._show_keyboard_for(watched)

            return False

        # A release outside the field is a cancelled tap (a drag, or a flick
        # gesture taking over); a popup already open (a long-press menu) wins.
        on_field = watched.rect().contains(event.position().toPoint())
        spin_box = editable_numeric_spin_box(watched)

        if (
            on_field
            and spin_box is not None
            and QApplication.activePopupWidget() is None
        ):
            SpinBoxPadSession(spin_box).open()

        return True

    def _open_pad_for_cell_editor(self, widget):
        """An inline numeric editor goes straight to the number pad."""

        if not isinstance(widget, NUMERIC_SPIN_BOXES):
            return

        if widget.property(PAD_OPENED_PROPERTY):
            return

        view, editor = item_view_cell(widget)

        if view is None or not is_delegate_editor(view, editor):
            return

        widget.setProperty(PAD_OPENED_PROPERTY, True)

        # Deferred so the view finishes opening the editor and focuses it;
        # bound to the widget, so a closed editor never gets a pad.
        QTimer.singleShot(0, widget, lambda: SpinBoxPadSession(widget).open())

    #### Adapting widgets #####################################################

    def _adapt(self, widget):
        mark_touch_fit(widget)

        if isinstance(widget, QAbstractSpinBox):
            self._adapt_spin_box(widget)

        elif isinstance(widget, QAbstractScrollArea):
            self._thin_scroll_bars(widget)
            self._add_flick_scrolling(widget)

    def _restore(self, widget):
        clear_touch_fit(widget)

        alignment = widget.property(ADAPTED_ALIGNMENT_PROPERTY)

        if alignment is not None:
            widget.setAlignment(Qt.AlignmentFlag(alignment))
            widget.setProperty(ADAPTED_ALIGNMENT_PROPERTY, None)

        minimum_width = widget.property(ADAPTED_MIN_WIDTH_PROPERTY)

        if minimum_width is not None:
            widget.setMinimumWidth(minimum_width)
            widget.setProperty(ADAPTED_MIN_WIDTH_PROPERTY, None)

        maximum_height = widget.property(ADAPTED_MAX_HEIGHT_PROPERTY)

        if maximum_height is not None:
            widget.setMaximumHeight(maximum_height)
            widget.setProperty(ADAPTED_MAX_HEIGHT_PROPERTY, None)

        if widget.property(ADAPTED_ACCELERATION_PROPERTY):
            widget.setAccelerated(False)
            widget.setProperty(ADAPTED_ACCELERATION_PROPERTY, None)

        if widget.property(FLICK_SCROLLING_PROPERTY):
            QScroller.ungrabGesture(widget)
            widget.setProperty(FLICK_SCROLLING_PROPERTY, None)

    def _adapt_spin_box(self, spin_box):
        """Centre the value, make room for the stepper's second button, hold
        it to the buttons' height, and accelerate held steps; compact spin
        boxes have no stepper, so they are left as they are."""

        if spin_box.property(TOUCH_COMPACT_PROPERTY):
            return

        if spin_box.property(ADAPTED_ALIGNMENT_PROPERTY) is None:
            spin_box.setProperty(ADAPTED_ALIGNMENT_PROPERTY, spin_box.alignment().value)
            spin_box.setAlignment(_STEPPER_ALIGNMENT)

        if spin_box.property(ADAPTED_MIN_WIDTH_PROPERTY) is None:
            minimum_width = spin_box.minimumWidth()
            spin_box.setProperty(ADAPTED_MIN_WIDTH_PROPERTY, minimum_width)

            # The stylesheet's size hint reserves room for one button only.
            spin_box.setMinimumWidth(
                max(minimum_width, spin_box.sizeHint().width() + TOUCH_TARGET_PX)
            )

        if spin_box.property(ADAPTED_MAX_HEIGHT_PROPERTY) is None:
            spin_box.setProperty(ADAPTED_MAX_HEIGHT_PROPERTY, spin_box.maximumHeight())

            # The stepper buttons are exactly the target tall, their frame
            # included, and a spin box held to that height is filled by
            # them edge to edge; only a font too tall for it grows it.
            needed_height = (
                spin_box.lineEdit().minimumSizeHint().height() + 2 * TOUCH_FRAME_PX
            )
            spin_box.setMaximumHeight(max(TOUCH_TARGET_PX, needed_height))

        if not spin_box.isAccelerated():
            spin_box.setAccelerated(True)
            spin_box.setProperty(ADAPTED_ACCELERATION_PROPERTY, True)

    def _thin_scroll_bars(self, area):
        """Mark the area's thin scroll bars and restyle them each time the
        area shows: the stylesheet can size a bar before its mark is set
        (for one, when the code sets the scroll-bar policy after the bar was
        first measured), and a mark alone never restyles."""

        for scroll_bar in thin_scroll_bars(area):
            scroll_bar.setProperty(TOUCH_COMPACT_PROPERTY, True)
            scroll_bar.style().unpolish(scroll_bar)
            scroll_bar.style().polish(scroll_bar)
            scroll_bar.updateGeometry()

    def _add_flick_scrolling(self, area):
        """Finger-flick scrolling, as the portable rig gives its panes at
        startup; the device canvas (a QGraphicsView) is excluded — drags
        there toggle electrodes and draw routes — and so are headers, whose
        sections are dragged to reorder and long-pressed for their menu."""
        viewport = area.viewport()

        if isinstance(area, (QGraphicsView, QHeaderView)):
            return

        if QScroller.hasScroller(viewport):
            return

        QScroller.grabGesture(viewport, QScroller.ScrollerGestureType.TouchGesture)
        viewport.setProperty(FLICK_SCROLLING_PROPERTY, True)

    #### Text fields ##########################################################

    def _show_keyboard_for(self, widget):
        """Bring up the Touch Assist keyboard for a tapped text field, along
        the screen edge away from the field."""
        field = editable_text_field(widget)

        if field is None:
            return

        # A keyboard the user opened from the menu stays where they put it.
        if touch_assist_manager.is_visible(TOOL_KEYBOARD) and not self._keyboard_shown:
            return

        field_rect = QRect(field.mapToGlobal(QPoint(0, 0)), field.size())
        touch_assist_manager.show_clear_of(TOOL_KEYBOARD, field_rect)
        self._keyboard_shown = True

    def _on_focus_changed(self, old, new):
        """Put the keyboard away once focus leaves text fields."""

        if not self._keyboard_shown or new is None:
            return

        if editable_text_field(new) is None:
            touch_assist_manager.set_visible(TOOL_KEYBOARD, False)
            self._keyboard_shown = False

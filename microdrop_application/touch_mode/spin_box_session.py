# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One number-pad edit of one spin box: opens the pad on the spin box's
range, and applies OK or cancel the way a keyboard user would."""

# Enthought library imports.
from pyface.qt.QtCore import QEvent, QObject, QPoint, QRect, Qt
from pyface.qt.QtGui import QKeyEvent
from pyface.qt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDoubleSpinBox,
    QSpinBox,
)

# Local imports.
from .number_entry import NumberEntry
from .number_pad import NumberPad

#: The spin boxes the number pad edits: the numeric ones.
NUMERIC_SPIN_BOXES = (QSpinBox, QDoubleSpinBox)


def item_view_cell(widget):
    """Return ``(view, editor)`` when ``widget`` sits in an item view's
    viewport, ``editor`` being its ancestor placed in the cell; else
    ``(None, None)``."""
    child = widget
    parent = widget.parentWidget()

    while parent is not None:
        view = parent.parentWidget()

        if isinstance(view, QAbstractItemView) and parent is view.viewport():
            return view, child

        child, parent = parent, view

    return None, None


def cell_index(view, editor):
    """Return the model index of the cell ``editor`` is placed in."""
    return view.indexAt(editor.geometry().center())


def is_delegate_editor(view, editor):
    """Whether ``editor`` is an inline editor the view's delegate opened, as
    opposed to a widget placed in the cell for good (``setIndexWidget``)."""
    index = cell_index(view, editor)

    persistent = view.isPersistentEditorOpen(index)

    return view.indexWidget(index) is editor and not persistent


class SpinBoxPadSession(QObject):
    """A child of the spin box being edited: should the spin box be
    destroyed while the pad is open, the session and the pad's answer go too.

    OK sets the value, then presses Enter on the spin box: consumers see
    ``valueChanged`` and ``editingFinished`` exactly as after typing, and an
    item-view delegate commits and closes its inline editor on that Enter.
    Cancel on an inline editor presses Esc, which closes it uncommitted.
    """

    def __init__(self, spin_box):
        super().__init__(spin_box)
        self._spin_box = spin_box

        view, editor = item_view_cell(spin_box)
        self._closes_editor = view is not None and is_delegate_editor(view, editor)
        self._title = ""

        if view is not None:
            self._title = str(
                view.model().headerData(
                    cell_index(view, editor).column(),
                    Qt.Orientation.Horizontal,
                    Qt.ItemDataRole.DisplayRole,
                )
                or ""
            )

    def open(self):
        """Show the number pad next to the spin box."""
        spin_box = self._spin_box
        decimals = 0

        if isinstance(spin_box, QDoubleSpinBox):
            decimals = spin_box.decimals()

        entry = NumberEntry(
            minimum=spin_box.minimum(), maximum=spin_box.maximum(), decimals=decimals
        )
        entry.start(spin_box.value())

        pad = NumberPad(
            entry,
            title=self._title,
            prefix=spin_box.prefix(),
            suffix=spin_box.suffix(),
            parent=spin_box.window(),
        )
        pad.accepted.connect(self._apply)
        pad.cancelled.connect(self._cancel)
        spin_box.destroyed.connect(pad.close)

        pad.popup_beside(QRect(spin_box.mapToGlobal(QPoint(0, 0)), spin_box.size()))

    def _apply(self, value):
        spin_box = self._spin_box

        if isinstance(spin_box, QSpinBox):
            value = round(value)

        spin_box.setValue(value)
        self._press_key(Qt.Key.Key_Return, "\r")
        self.deleteLater()

    def _cancel(self):
        if self._closes_editor:
            self._press_key(Qt.Key.Key_Escape, "\x1b")

        self.deleteLater()

    def _press_key(self, key, text):
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(
                self._spin_box,
                QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier, text),
            )

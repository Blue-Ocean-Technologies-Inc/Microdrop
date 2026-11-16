# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""How each widget takes the touch stylesheet, decided from the sizes its
code gave it and marked as a dynamic property the stylesheet matches on.

A widget sized freely in code grows to finger size; one held to a size in
code (an icon button in a grid, a spin box in a 20 px status row, a cell
editor) keeps that size, since growing would clip its content.
"""

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QTabBar,
    QToolButton,
)

# Microdrop style imports.
from microdrop_style.touch_style import (
    TOUCH_COMPACT_PROPERTY,
    TOUCH_GROWS_PROPERTY,
    TOUCH_TARGET_PX,
)

# Local imports.
from .consts import STEPPER_MIN_WIDTH_PX, UNCONSTRAINED_SIZE_PX
from .spin_box_session import item_view_cell

#: Widgets that grow by padding only when their code left their size free.
_GROWING_WIDGETS = (QPushButton, QToolButton, QLineEdit)


def is_size_free(widget):
    """Whether code left the widget's maximum size unconstrained."""
    return (
        widget.maximumHeight() >= UNCONSTRAINED_SIZE_PX
        and widget.maximumWidth() >= UNCONSTRAINED_SIZE_PX
    )


def thin_scroll_bars(area):
    """Return the scroll bars of ``area`` that stay thin in touch mode.

    A QScrollArea pane is flicked by its content, and a finger-thick bar
    would take its width: its content then clips and scrolls sideways. A
    strip scrolling only sideways (a status read-out, a button row) would
    have its content covered. Item views keep finger-thick bars.
    """

    if isinstance(area, QScrollArea):
        return (area.verticalScrollBar(), area.horizontalScrollBar())

    if area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
        return (area.horizontalScrollBar(),)

    return ()


def scroll_area_of(scroll_bar):
    """Return the scroll area ``scroll_bar`` belongs to, or None; Qt keeps
    the bars in containers between the two."""

    ancestor = scroll_bar.parentWidget()

    for _ in range(2):
        if ancestor is None or isinstance(ancestor, QAbstractScrollArea):
            return ancestor

        ancestor = ancestor.parentWidget()

    return None


def is_compact(widget):
    """Whether the widget cannot take its finger size: a spin box in a cell
    or held smaller than a stepper, a combo box held low, or a scroll bar
    that stays thin (see thin_scroll_bars)."""

    if isinstance(widget, QAbstractSpinBox):
        return (
            widget.maximumHeight() < TOUCH_TARGET_PX
            or widget.maximumWidth() < STEPPER_MIN_WIDTH_PX
            or item_view_cell(widget)[0] is not None
        )

    if isinstance(widget, QComboBox):
        return widget.maximumHeight() < TOUCH_TARGET_PX

    if isinstance(widget, QScrollBar):
        area = scroll_area_of(widget)

        return area is not None and widget in thin_scroll_bars(area)

    return False


def grows(widget):
    """Whether the widget grows to finger size by padding: a button or a
    text field its code left free to size (a spin box's or combo box's own
    line edit is part of that control, not a field, and a tab bar sizes its
    own scroll arrows)."""

    if not isinstance(widget, _GROWING_WIDGETS) or not is_size_free(widget):
        return False

    owned_by = (QAbstractSpinBox, QComboBox, QTabBar)

    return not isinstance(widget.parentWidget(), owned_by)


def mark_touch_fit(widget):
    """Mark the widget compact or growing, as it takes the touch style."""

    if is_compact(widget):
        widget.setProperty(TOUCH_COMPACT_PROPERTY, True)

    elif grows(widget):
        widget.setProperty(TOUCH_GROWS_PROPERTY, True)


def clear_touch_fit(widget):
    """Remove the marks mark_touch_fit set."""

    for name in (TOUCH_COMPACT_PROPERTY, TOUCH_GROWS_PROPERTY):
        if widget.property(name) is not None:
            widget.setProperty(name, None)

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What is at a point on screen, and its help text: the tooltip of the
control under it, resolved generously.

Resolution goes by geometry, not by event receiver, so disabled controls
(which get no mouse events) resolve too: an item view cell's or header
section's tooltip role, a tab's tooltip, a graphics item's tooltip, a
TraitsUI label's editor tooltip, else the nearest widget up the parent
chain that has one.
"""

# Enthought library imports.
from pyface.qt.QtCore import QRect, Qt
from pyface.qt.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTabBar,
    QWidget,
)
from traits.api import HasTraits, Instance, Str

# Local imports.
from .consts import HELP_TITLE_MAX_CHARS, ICON_FONT_FAMILY_PREFIXES


class HelpTopic(HasTraits):
    """The help for one control or item under the finger."""

    #: Short bold heading (button text, label text, column header); may be
    #: empty.
    title = Str()

    #: The help text; empty when the control has none.
    text = Str()

    #: Global rectangle of the control or item the topic is about.
    anchor = Instance(QRect)

    #: The widget the anchor lies in, whose window the outline is drawn on.
    widget = Instance(QWidget)

    def same_as(self, other):
        """Whether ``other`` is the same help on the same spot."""
        return (
            other is not None
            and (self.title, self.text) == (other.title, other.text)
            and self.anchor == other.anchor
        )


def widget_at(global_point, window=None):
    """The widget at ``global_point`` in ``window`` (the window the touch
    landed in), disabled ones included; without a window, the topmost on
    screen there."""

    if window is None:
        return QApplication.widgetAt(global_point)

    return window.childAt(window.mapFromGlobal(global_point)) or window


def resolve_help(global_point, window=None, ignored_windows=()):
    """Return the HelpTopic for what is at ``global_point`` (in ``window``
    when given), or None when nothing, or one of ``ignored_windows``, is
    there."""
    widget = widget_at(global_point, window)

    if widget is None or widget.window() in ignored_windows:
        return None

    point = widget.mapFromGlobal(global_point)

    for item_topic in (_item_view_topic, _tab_bar_topic, _graphics_item_topic):
        topic = item_topic(widget, point)

        if topic is not None:
            return topic

    return _widget_topic(widget)


def global_rect(widget, rect=None):
    """Map ``rect`` (default: the whole widget) from ``widget`` to global."""
    rect = widget.rect() if rect is None else rect

    return QRect(widget.mapToGlobal(rect.topLeft()), rect.size())


def tooltip_text(value):
    """Plain help text from a tooltip role value (None, str, anything)."""
    return "" if value is None else str(value).strip()


def title_of(widget):
    """A short heading for ``widget``: its button, label or group title;
    empty for icon-font glyph buttons, rich text and long text."""
    title = ""

    if isinstance(widget, QAbstractButton):
        family = widget.font().family()

        if not family.startswith(ICON_FONT_FAMILY_PREFIXES):
            title = widget.text()

    elif isinstance(widget, QLabel) and widget.textFormat() != Qt.TextFormat.RichText:
        title = widget.text()

    elif isinstance(widget, QGroupBox):
        title = widget.title()

    title = title.replace("&", "").strip().rstrip(":").strip()

    if len(title) > HELP_TITLE_MAX_CHARS or "<" in title:
        return ""

    return title


#### Items inside widgets ####################################################


def _item_view_topic(widget, point):
    """A cell's or a header section's tooltip role, when it has one."""
    view = widget.parentWidget()

    if not isinstance(view, QAbstractItemView) or widget is not view.viewport():
        return None

    if isinstance(view, QHeaderView):
        return _header_topic(view, point)

    index = view.indexAt(point)

    if not index.isValid():
        return None

    text = tooltip_text(index.data(Qt.ItemDataRole.ToolTipRole))

    if not text:
        return None

    header = view.model().headerData(
        index.column(), Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
    )

    return HelpTopic(
        title=tooltip_text(header),
        text=text,
        anchor=global_rect(view.viewport(), view.visualRect(index)),
        widget=view,
    )


def _header_topic(header, point):
    section = header.logicalIndexAt(point)

    if section < 0:
        return None

    model = header.model()
    text = tooltip_text(
        model.headerData(section, header.orientation(), Qt.ItemDataRole.ToolTipRole)
    )

    if not text:
        return None

    position = header.sectionViewportPosition(section)
    size = header.sectionSize(section)

    if header.orientation() == Qt.Orientation.Horizontal:
        rect = QRect(position, 0, size, header.viewport().height())
    else:
        rect = QRect(0, position, header.viewport().width(), size)

    title = model.headerData(section, header.orientation(), Qt.ItemDataRole.DisplayRole)

    return HelpTopic(
        title=tooltip_text(title),
        text=text,
        anchor=global_rect(header.viewport(), rect),
        widget=header,
    )


def _tab_bar_topic(widget, point):
    if not isinstance(widget, QTabBar):
        return None

    tab = widget.tabAt(point)

    if tab < 0 or not widget.tabToolTip(tab):
        return None

    return HelpTopic(
        title=widget.tabText(tab).replace("&", ""),
        text=widget.tabToolTip(tab),
        anchor=global_rect(widget, widget.tabRect(tab)),
        widget=widget,
    )


def _graphics_item_topic(widget, point):
    """The tooltip of the topmost graphics item there (or of an item it is
    part of), as electrodes in the device viewer carry."""
    view = widget.parentWidget()

    if not isinstance(view, QGraphicsView) or widget is not view.viewport():
        return None

    for item in view.items(point):
        owner = item

        while owner is not None and not owner.toolTip():
            owner = owner.parentItem()

        if owner is None:
            continue

        rect = view.mapFromScene(owner.sceneBoundingRect()).boundingRect()

        return HelpTopic(
            text=owner.toolTip(),
            anchor=global_rect(view.viewport(), rect),
            widget=view,
        )

    return None


#### Widgets #################################################################


def _widget_topic(widget):
    """The nearest tooltip up the parent chain. A TraitsUI item's label and
    editor sit side by side in a layout row: the label speaks for the
    editor's tooltip, and the editor takes the label as its title. With no
    tooltip anywhere the topic has no text."""
    owner = widget

    while owner is not None:
        editor = _layout_neighbour(owner, 1) if isinstance(owner, QLabel) else None

        if (
            editor is not None
            and editor.toolTip()
            and editor.toolTip() != owner.toolTip()
        ):
            return HelpTopic(
                title=title_of(owner),
                text=editor.toolTip(),
                anchor=global_rect(owner),
                widget=owner,
            )

        if owner.toolTip():
            label = _layout_neighbour(owner, -1)
            title = title_of(owner)

            if not title and isinstance(label, QLabel):
                title = title_of(label)

            return HelpTopic(
                title=title,
                text=owner.toolTip(),
                anchor=global_rect(owner),
                widget=owner,
            )

        if owner.isWindow():
            break

        owner = owner.parentWidget()

    return HelpTopic(title=title_of(widget), anchor=global_rect(widget), widget=widget)


def _layout_neighbour(widget, step):
    """The widget ``step`` places after (or, negative, before) ``widget``
    in its layout row; None when there is none."""

    if widget.parentWidget() is None:
        return None

    layout = _layout_holding(widget.parentWidget().layout(), widget)

    if isinstance(layout, QGridLayout):
        row, column, _rows, _columns = layout.getItemPosition(layout.indexOf(widget))
        item = layout.itemAtPosition(row, column + step)

    elif isinstance(layout, QBoxLayout):
        index = layout.indexOf(widget) + step
        item = layout.itemAt(index) if 0 <= index < layout.count() else None

    else:
        item = None

    return None if item is None else item.widget()


def _layout_holding(layout, widget):
    """The layout, nested anywhere in ``layout``, that holds ``widget``."""

    if layout is None:
        return None

    if layout.indexOf(widget) >= 0:
        return layout

    for index in range(layout.count()):
        found = _layout_holding(layout.itemAt(index).layout(), widget)

        if found is not None:
            return found

    return None

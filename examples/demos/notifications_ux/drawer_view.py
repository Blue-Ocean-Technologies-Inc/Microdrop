# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The prototype's drawer: the product's fixed, translucent right-hand
drawer, with a left edge that drags its width and a header (title, count,
Mark all read, Clear all, Close) over one scrolling column of sections
(``column_view``).

The product host still opens, closes, slides and places it; the subclasses
here only swap in the contents and the width.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Bool, HasTraits, Instance, observe

# Microdrop package imports.
from notifications.views.drawer import NotificationsDrawer, anchored_drawer_rect
from notifications.views.drawer_host import NotificationsDrawerHost, _EventRelay

# Microdrop style imports.
from microdrop_style.colors import INFO_COLOR
from microdrop_style.icons.icons import ICON_CLOSE, ICON_DELETE_SWEEP, ICON_DONE_ALL

# Local imports.
from .ux_consts import (
    DRAWER_GRIP_WIDTH,
    DRAWER_MAX_WIDTH,
    DRAWER_MIN_WIDTH,
)
from .ux_models import UxPaneModel
from .view_styles import (
    icon_button_style,
    readable_accent,
    text_font,
    with_alpha,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Object name of the sections' area, behind which the drawer is translucent.
SECTIONS_OBJECT_NAME = "notifications_ux.sections"

#: Room (px) the widest drawer leaves of the window on its left.
WINDOW_LEFT_IN_VIEW = 160


def drawer_width_for(window_width, wanted):
    """The drawer's width in a ``window_width`` window, for ``wanted``."""
    widest = max(
        min(DRAWER_MAX_WIDTH, window_width - WINDOW_LEFT_IN_VIEW), DRAWER_MIN_WIDTH
    )

    return min(max(wanted, DRAWER_MIN_WIDTH), widest, window_width)


class _EdgeGrip(QtWidgets.QWidget):
    """The drawer's left edge: drag to resize. ``width_requested`` carries
    the drawer width the drag asks for."""

    width_requested = QtCore.Signal(int)

    def __init__(self, drawer):
        super().__init__(drawer)

        self._drawer = drawer
        self._press = None

        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip("Drag to resize")

    def paintEvent(self, event):

        if not self.underMouse() and self._press is None:
            return

        painter = QtGui.QPainter(self)
        painter.fillRect(QtCore.QRect(0, 0, 3, self.height()), QtGui.QColor(INFO_COLOR))

    def mousePressEvent(self, event):
        self._press = (event.globalPosition().x(), self._drawer.width())
        event.accept()

    def mouseMoveEvent(self, event):

        if self._press is not None:
            start_x, start_width = self._press
            self.width_requested.emit(
                int(start_width - (event.globalPosition().x() - start_x))
            )

        event.accept()

    def mouseReleaseEvent(self, event):
        self._press = None
        self.update()
        event.accept()


class UxDrawer(NotificationsDrawer):
    """The product drawer with a draggable left edge."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.edge = _EdgeGrip(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.edge.setGeometry(0, 0, DRAWER_GRIP_WIDTH, self.height())
        self.edge.raise_()


class DrawerHeader(QtWidgets.QWidget):
    """Title, count chip, and the drawer's three buttons."""

    def __init__(self, model, parent=None):
        super().__init__(parent)

        self.model = model

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 4, 8)
        layout.setSpacing(2)

        self._title = QtWidgets.QLabel("Notifications", self)
        self._title.setFont(text_font(self.font(), 3.0, QtGui.QFont.Weight.Bold))
        layout.addWidget(self._title)
        layout.addSpacing(8)

        self._chip = QtWidgets.QLabel(self)
        layout.addWidget(self._chip, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

        self.mark_all_read = self._button(
            ICON_DONE_ALL, "Mark all read", "mark_all_read_button"
        )
        self.clear_all = self._button(
            ICON_DELETE_SWEEP, "Clear all (keeps Needs attention)", "clear_all_button"
        )
        self.close = self._button(ICON_CLOSE, "Close (Esc)", "close_button")

        for button in (self.mark_all_read, self.clear_all, self.close):
            layout.addWidget(button)

        self.restyle()

    def _button(self, glyph, tooltip, model_button):
        button = QtWidgets.QToolButton(self)
        button.setText(glyph)
        button.setToolTip(tooltip)
        button.setFixedSize(32, 32)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: setattr(self.model, model_button, True))

        return button

    def show_counts(self, total, new, attention):
        """Show the count chip and enable the buttons that would do
        anything."""

        if new:
            text = f"{new} new"

        elif total:
            text = str(total)

        else:
            text = ""

        self._chip.setText(text)
        self._chip.setVisible(bool(text))
        self.mark_all_read.setEnabled(bool(new))
        self.clear_all.setEnabled(total > attention)

    def restyle(self):
        palette = self.palette()
        accent = readable_accent(INFO_COLOR, palette)
        tint = with_alpha(INFO_COLOR, 0.16).name(QtGui.QColor.NameFormat.HexArgb)

        self._chip.setFont(text_font(self.font(), -1.0, QtGui.QFont.Weight.DemiBold))
        self._chip.setStyleSheet(
            f"color: {accent.name()}; background: {tint};"
            " border-radius: 9px; padding: 1px 8px;"
        )

        for button in (self.mark_all_read, self.clear_all, self.close):
            button.setStyleSheet(icon_button_style(palette, 20))

    def changeEvent(self, event):
        super().changeEvent(event)

        if event.type() == QtCore.QEvent.Type.PaletteChange:
            self.restyle()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        text = self.palette().color(QtGui.QPalette.ColorRole.Text)
        painter.setPen(with_alpha(text, 0.1))
        painter.drawLine(8, self.height() - 1, self.width() - 4, self.height() - 1)


class _ContentsBinding(HasTraits):
    """Keeps the header's counts current."""

    model = Instance(UxPaneModel)

    view = Any()

    #: Whether a refresh is queued.
    _queued = Bool(False)

    @observe("model:center:entries.items.[is_new, needs_attention, unread]")
    @observe("model:center:bulk_changed")
    def _show_counts(self, event):
        """Once the current burst of changes is done."""

        if not self._queued:
            self._queued = True
            QtCore.QTimer.singleShot(0, self._refresh)

    def _refresh(self):
        self._queued = False

        if self.model is not None:
            self.view.show_counts()


class UxDrawerHost(NotificationsDrawerHost):
    """The product host, with the prototype's drawer, contents and width."""

    model = Instance(UxPaneModel)

    def attach(self, window):
        """Put a UxDrawer on ``window``; as the product host otherwise."""
        self.detach()

        self.window = window
        self.drawer = drawer = UxDrawer(window)
        drawer.hide()
        drawer.close_requested.connect(self._close_from_view)
        drawer.edge.width_requested.connect(self._resize_to)

        self._slide = QtCore.QPropertyAnimation(drawer, b"pos", drawer)
        self._slide.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)

        self._window_relay = _EventRelay(self._on_window_event, window)
        window.installEventFilter(self._window_relay)
        window.destroyed.connect(self._forget_window)

        if self.model.is_open:
            self._open()

    def _build_contents(self):
        from .column_view import ColumnDrawerView

        self._ui = self.model.edit_traits(
            view=ColumnDrawerView, kind="subpanel", parent=self.drawer
        )
        contents = self._ui.control
        area = contents.findChild(QtWidgets.QWidget, SECTIONS_OBJECT_NAME)

        self.drawer.set_contents(contents, translucent_area=area)

    def _place(self):
        """Anchor the drawer as the product does, at the model's width."""
        rect = anchored_drawer_rect(self.window)
        width = drawer_width_for(self.window.width(), self.model.drawer_width)
        rect.setLeft(self.window.width() - width)

        if self._slide.state() == QtCore.QAbstractAnimation.State.Running:
            self._slide.setEndValue(rect.topLeft())
            self.drawer.resize(rect.size())

        else:
            self.drawer.setGeometry(rect)

        return rect

    def _resize_to(self, width):
        self.model.drawer_width = drawer_width_for(self.window.width(), width)

    @observe("model:drawer_width")
    def _follow_width(self, event):

        if self.drawer is not None and self.drawer.isVisible():
            self._place()

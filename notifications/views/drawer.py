# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications drawer's panel: the drawer's contents on a background
that is opaque behind the header and sections and faintly translucent
behind the cards, with a border along its left edge.

It is a plain child of the main window, not a dock widget, so it lays over
the panes instead of moving them. NotificationsDrawerHost places it, opens
and closes it, and turns it opaque when what lies beneath keeps changing;
the panel itself only paints, keeps the clicks it receives, and asks to
close on Esc.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Local imports.
from ..consts import (
    DRAWER_OBJECT_NAME,
    DRAWER_OPACITY,
    DRAWER_PADDING_PX,
    DRAWER_WIDTH,
)

_ROLE = QtGui.QPalette.ColorRole

_DIRECT_CHILDREN = QtCore.Qt.FindChildOption.FindDirectChildrenOnly


def anchored_drawer_rect(window):
    """Where the drawer goes on ``window`` (a QMainWindow): at its right
    edge, between the menu bar and top toolbars above and the status bar
    below, as wide as DRAWER_WIDTH or the window if that is narrower."""
    top = 0
    bottom = window.height()
    menu = window.menuWidget()

    if menu is not None and menu.isVisible():
        top = menu.geometry().bottom() + 1

    for toolbar in window.findChildren(QtWidgets.QToolBar, options=_DIRECT_CHILDREN):
        in_top_area = (
            window.toolBarArea(toolbar) == QtCore.Qt.ToolBarArea.TopToolBarArea
        )

        if toolbar.isVisible() and not toolbar.isFloating() and in_top_area:
            top = max(top, toolbar.geometry().bottom() + 1)

    # Looked up, not window.statusBar(), which would create one.
    status_bar = window.findChild(QtWidgets.QStatusBar, options=_DIRECT_CHILDREN)

    if status_bar is not None and status_bar.isVisible():
        bottom = status_bar.geometry().top()

    width = min(DRAWER_WIDTH, window.width())

    return QtCore.QRect(window.width() - width, top, width, max(bottom - top, 0))


class NotificationsDrawer(QtWidgets.QWidget):
    """The drawer panel; its contents go in with ``set_contents``."""

    #: Esc pressed while the drawer has the focus.
    close_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName(DRAWER_OBJECT_NAME)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        #: Below this widget's top the background is translucent; None
        #: keeps it all opaque.
        self._translucent_area = None

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(
            DRAWER_PADDING_PX + 1, DRAWER_PADDING_PX, DRAWER_PADDING_PX, 0
        )
        self._layout.setSpacing(0)

        escape = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        escape.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.close_requested)

    def set_contents(self, contents, translucent_area=None):
        """Show ``contents``; the background behind ``translucent_area`` (a
        transparent widget among them) lets what lies beneath show."""
        self._layout.addWidget(contents)
        self._translucent_area = translucent_area

    def is_translucent(self):
        """Whether any of the background is translucent now."""
        opaque = self.testAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent)

        return self._has_translucent_area() and not opaque

    def set_translucent(self, translucent):
        """Let what lies beneath show behind the cards, or not. Opaque, the
        panel tells Qt so, which then stops painting what lies beneath."""
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, not translucent
        )
        self.update()

    def paintEvent(self, event):
        """Opaque down to the translucent area, then translucent, then the
        left border on top."""
        painter = QtGui.QPainter(self)
        color = self.palette().color(_ROLE.Window)
        split = self.height()

        if self.is_translucent():
            area = self._translucent_area
            split = area.mapTo(self, QtCore.QPoint(0, 0)).y()

        painter.fillRect(0, 0, self.width(), split, color)

        if split < self.height():
            color.setAlphaF(DRAWER_OPACITY)
            painter.fillRect(0, split, self.width(), self.height() - split, color)

        painter.setPen(self.palette().color(_ROLE.Mid))
        painter.drawLine(0, 0, 0, self.height())

    def _has_translucent_area(self):

        if self._translucent_area is None or DRAWER_OPACITY >= 1.0:
            return False

        # Deleted with the contents.
        try:
            return self._translucent_area.isVisible()

        except RuntimeError:
            self._translucent_area = None

            return False

    # Kept here, not passed on to the main window: under the drawer may lie a
    # dock separator, which a press would otherwise start dragging.
    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

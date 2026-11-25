# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications drawer's panel: a floating panel with rounded corners,
opaque behind its header and faintly translucent behind its sections, with
a left edge that drags its width.

It is a plain child of the main window, not a dock widget, so it lies over
the panes instead of moving them. NotificationsDrawerHost places it, opens
and closes it, and turns it opaque when what lies beneath keeps changing;
the panel itself only paints, reports its repaints, keeps the clicks it
receives, and asks to close on Esc.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Local imports.
from .theme import theme_palette
from .view_consts import (
    DRAWER_GRIP_WIDTH,
    DRAWER_OBJECT_NAME,
    DRAWER_OPACITY,
    DRAWER_PADDING_PX,
    DRAWER_RADIUS,
)

_ROLE = QtGui.QPalette.ColorRole

_DIRECT_CHILDREN = QtCore.Qt.FindChildOption.FindDirectChildrenOnly

#: Width (px) of the grip's line while hovered or dragged.
GRIP_LINE_WIDTH = 3


def anchored_drawer_rect(window):
    """The room for the drawer on ``window`` (a QMainWindow): its full width,
    between the menu bar and top toolbars above and the status bar below."""
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

    return QtCore.QRect(0, top, window.width(), max(bottom - top, 0))


class EdgeGrip(QtWidgets.QWidget):
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
        line = QtCore.QRect(0, 0, GRIP_LINE_WIDTH, self.height())
        painter.fillRect(line, theme_palette().color(_ROLE.Highlight))

    def mousePressEvent(self, event):
        self._press = (event.globalPosition().x(), self._drawer.width())
        event.accept()

    def mouseMoveEvent(self, event):

        if self._press is not None:
            start_x, start_width = self._press
            moved = event.globalPosition().x() - start_x
            self.width_requested.emit(int(start_width - moved))

        event.accept()

    def mouseReleaseEvent(self, event):
        self._press = None
        self.update()
        event.accept()


class NotificationsDrawer(QtWidgets.QWidget):
    """The drawer panel; its contents go in with ``set_contents``."""

    #: Esc pressed while the drawer has the focus.
    close_requested = QtCore.Signal()

    #: The panel was repainted: with a translucent background, that is also
    #: what lies beneath repainting.
    painted = QtCore.Signal()

    #: The application's palette changed: a theme switch.
    theme_changed = QtCore.Signal()

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

        self.edge = EdgeGrip(self)

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
        """Let what lies beneath show behind the sections, or not. Opaque,
        the panel tells Qt so, which then stops painting what lies beneath."""
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, not translucent
        )
        self.update()

    def outline(self):
        """The panel's rounded outline."""
        path = QtGui.QPainterPath()
        path.addRoundedRect(
            QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            DRAWER_RADIUS,
            DRAWER_RADIUS,
        )

        return path

    def paintEvent(self, event):
        """Opaque down to the translucent area, then translucent, within
        rounded corners and a hairline border."""
        palette = theme_palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        outline = self.outline()
        color = palette.color(_ROLE.Window)
        split = self.height()

        if self.is_translucent():
            split = self._translucent_area.mapTo(self, QtCore.QPoint(0, 0)).y()

        painter.setClipPath(outline)
        painter.fillRect(0, 0, self.width(), split, color)

        if split < self.height():
            color.setAlphaF(DRAWER_OPACITY)
            painter.fillRect(0, split, self.width(), self.height() - split, color)

        painter.setClipping(False)
        painter.setPen(QtGui.QPen(palette.color(_ROLE.Mid)))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(outline)
        painter.end()

        self.painted.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.edge.setGeometry(0, 0, DRAWER_GRIP_WIDTH, self.height())
        self.edge.raise_()

        # Clicks and paint outside the corners reach what lies beneath.
        self.setMask(QtGui.QRegion(self.outline().toFillPolygon().toPolygon()))

    def event(self, event):

        if event.type() == QtCore.QEvent.Type.ApplicationPaletteChange:
            self.theme_changed.emit()

        return super().event(event)

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

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The connections editor's canvas: the zoom/pan image view of the
camera-alignment panes, with the left button routed by what it lands on —
a centroid dot drags out a new connection, a line selects it (Ctrl
toggles), Shift drags a selection box, anything else pans."""

# Enthought library imports.
from pyface.qt.QtCore import QRect, Qt, Signal
from pyface.qt.QtWidgets import QGraphicsView

# Local imports.
from ...consts import CONNECTIONS_EDITOR_PICK_TOLERANCE_PX
from ..camera_alignment_view.zoom_pan_view import ZoomPanImageView
from .connections_overlay import ConnectionLineItem


class ConnectionsCanvasView(ZoomPanImageView):
    #: Delete or Backspace was pressed over the canvas.
    delete_requested = Signal()
    #: Ctrl+Z was pressed over the canvas.
    undo_requested = Signal()
    #: Ctrl+Shift+Z or Ctrl+Y was pressed over the canvas.
    redo_requested = Signal()

    def __init__(self, pixmap, parent=None):
        super().__init__(pixmap, parent)
        #: The ConnectionsOverlay on this canvas's scene; the owner
        #: sets it once the overlay exists.
        self.overlay = None
        self._drawing_line = False

        # Key presses (Delete) only arrive with focus.
        self.setFocusPolicy(Qt.StrongFocus)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self.overlay is None:
            super().mousePressEvent(event)
            return

        position = event.position().toPoint()

        if self.overlay.begin_line(self.mapToScene(position)):
            self._drawing_line = True
            return

        line_item = self._line_item_near(position)

        if line_item is not None:
            if event.modifiers() & Qt.ControlModifier:
                line_item.setSelected(not line_item.isSelected())
            else:
                self.scene().clearSelection()
                line_item.setSelected(True)

            return

        if event.modifiers() & Qt.ShiftModifier:
            # Straight to QGraphicsView: the parent class would turn
            # this press into a pan.
            self.setDragMode(QGraphicsView.RubberBandDrag)
            QGraphicsView.mousePressEvent(self, event)

            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing_line:
            self.overlay.update_line(self.mapToScene(event.position().toPoint()))
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drawing_line and event.button() == Qt.LeftButton:
            self._drawing_line = False
            self.overlay.finish_line(self.mapToScene(event.position().toPoint()))
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_requested.emit()
            return

        if event.modifiers() & Qt.ControlModifier and event.key() in (
            Qt.Key_Z,
            Qt.Key_Y,
        ):
            if event.key() == Qt.Key_Y or event.modifiers() & Qt.ShiftModifier:
                self.redo_requested.emit()
            else:
                self.undo_requested.emit()
            return

        super().keyPressEvent(event)

    def _line_item_near(self, position):
        """The topmost connection line within the pick tolerance (view
        pixels) of ``position``, or None."""
        tolerance = CONNECTIONS_EDITOR_PICK_TOLERANCE_PX
        pick_rect = QRect(
            position.x() - tolerance,
            position.y() - tolerance,
            2 * tolerance,
            2 * tolerance,
        )

        return next(
            (
                item
                for item in self.items(pick_rect)
                if isinstance(item, ConnectionLineItem)
            ),
            None,
        )

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The region picker's canvas: the captured frame in the camera-alignment
zoom/pan view, with the region drawn over it as an orange frame with
corner dots and the rest of the frame shaded.

The canvas only translates the mouse: a left press or drag goes to the
picker model in frame fractions (the model decides what it grabs), a
right or middle drag pans, and the wheel zooms. The overlay draws
whatever region the dialog's controller hands it."""

# Enthought library imports.
from pyface.qt.QtCore import QPointF, QRectF, Qt
from pyface.qt.QtGui import QBrush, QColor, QPainterPath, QPen
from pyface.qt.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
)

# Local imports.
from ...consts import (
    LIVE_HISTOGRAM_REGION_FRAME_COLOR_HEX,
    LIVE_HISTOGRAM_REGION_FRAME_WIDTH_PX,
    LIVE_HISTOGRAM_REGION_GRAB_PX,
    LIVE_HISTOGRAM_REGION_HANDLE_COLOR_HEX,
    LIVE_HISTOGRAM_REGION_HANDLE_RADIUS_PX,
    LIVE_HISTOGRAM_REGION_HANDLE_RING_COLOR_HEX,
    LIVE_HISTOGRAM_REGION_SHADE_ALPHA,
    LIVE_HISTOGRAM_REGION_SHADE_COLOR_HEX,
)
from ..camera_alignment_view.zoom_pan_view import ZoomPanImageView
from .region import ALL_SIDES, grabbed_sides

#: The pointer shape over each grab: the sorted side indices a press there
#: would take hold of (see ``region.grabbed_sides``).
GRAB_CURSORS = {
    (0,): Qt.CursorShape.SizeHorCursor,
    (2,): Qt.CursorShape.SizeHorCursor,
    (1,): Qt.CursorShape.SizeVerCursor,
    (3,): Qt.CursorShape.SizeVerCursor,
    (0, 1): Qt.CursorShape.SizeFDiagCursor,
    (2, 3): Qt.CursorShape.SizeFDiagCursor,
    (1, 2): Qt.CursorShape.SizeBDiagCursor,
    (0, 3): Qt.CursorShape.SizeBDiagCursor,
    ALL_SIDES: Qt.CursorShape.SizeAllCursor,
}

#: Above the frame image.
OVERLAY_Z_VALUE = 50.0


class RegionOverlay:
    """The region's frame, its four corner dots, and the shade outside it,
    managed as one unit on a QGraphicsScene whose coordinates are frame
    pixels."""

    def __init__(self, scene):
        self._scene = scene

        self._shade = QGraphicsPathItem()
        shade_color = QColor(LIVE_HISTOGRAM_REGION_SHADE_COLOR_HEX)
        shade_color.setAlphaF(LIVE_HISTOGRAM_REGION_SHADE_ALPHA)
        self._shade.setBrush(QBrush(shade_color))
        self._shade.setPen(QPen(Qt.PenStyle.NoPen))
        self._shade.setZValue(OVERLAY_Z_VALUE)
        scene.addItem(self._shade)

        self._frame = QGraphicsRectItem()
        pen = QPen(
            QColor(LIVE_HISTOGRAM_REGION_FRAME_COLOR_HEX),
            LIVE_HISTOGRAM_REGION_FRAME_WIDTH_PX,
        )
        pen.setCosmetic(True)  # constant width at any zoom
        self._frame.setPen(pen)
        self._frame.setZValue(OVERLAY_Z_VALUE + 1)
        scene.addItem(self._frame)

        radius = LIVE_HISTOGRAM_REGION_HANDLE_RADIUS_PX
        self._handles = []

        for _ in range(4):
            # The dots only show the corners: presses reach the canvas,
            # which grabs by distance at any zoom.
            handle = QGraphicsEllipseItem(-radius, -radius, 2 * radius, 2 * radius)
            handle.setBrush(QBrush(QColor(LIVE_HISTOGRAM_REGION_HANDLE_COLOR_HEX)))
            handle.setPen(QPen(QColor(LIVE_HISTOGRAM_REGION_HANDLE_RING_COLOR_HEX), 2))
            handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            handle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            handle.setZValue(OVERLAY_Z_VALUE + 2)
            scene.addItem(handle)
            self._handles.append(handle)

    def set_region(self, region, frame_size):
        """Draw ``region`` (frame fractions) over a frame of ``frame_size``."""
        frame_width, frame_height = frame_size
        left, top, right, bottom = region

        rect = QRectF(
            QPointF(left * frame_width, top * frame_height),
            QPointF(right * frame_width, bottom * frame_height),
        )
        self._frame.setRect(rect)

        shade = QPainterPath()
        shade.addRect(QRectF(0, 0, frame_width, frame_height))
        shade.addRect(rect)
        self._shade.setPath(shade)

        corners = (
            rect.topLeft(),
            rect.topRight(),
            rect.bottomRight(),
            rect.bottomLeft(),
        )

        for handle, corner in zip(self._handles, corners):
            handle.setPos(corner)

    def frame_rect(self):
        """The drawn region, in frame pixels."""
        return self._frame.rect()


class RegionCanvas(ZoomPanImageView):
    """The frame in the zoom/pan view, editing the picker model's region:
    left drags draw, resize, and move it; right or middle drags pan."""

    def __init__(self, pixmap, picker, parent=None):
        super().__init__(pixmap, parent)

        #: The RegionPickerModel the drags edit.
        self._picker = picker

        #: The view position a pan drag last reached; None between pans.
        self._pan_position = None

        # Hover feedback: the pointer shows what a press would grab.
        self.viewport().setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._picker.begin_drag(self._frame_point(event), self._grab_tolerance())

        elif event.button() in (
            Qt.MouseButton.RightButton,
            Qt.MouseButton.MiddleButton,
        ):
            self._pan_position = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._picker.drag_to(self._frame_point(event))

        elif self._pan_position is not None:
            delta = event.position() - self._pan_position
            self._pan_position = event.position()

            horizontal, vertical = self.horizontalScrollBar(), self.verticalScrollBar()
            horizontal.setValue(horizontal.value() - round(delta.x()))
            vertical.setValue(vertical.value() - round(delta.y()))

        else:
            sides = grabbed_sides(
                self._picker.region, self._frame_point(event), self._grab_tolerance()
            )
            self.viewport().setCursor(
                GRAB_CURSORS.get(sides, Qt.CursorShape.CrossCursor)
            )

        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._picker.end_drag()

        else:
            self._pan_position = None
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)

        event.accept()

    def frame_size(self):
        """(width, height) of the shown frame, in pixels."""
        rect = self.sceneRect()

        return max(rect.width(), 1.0), max(rect.height(), 1.0)

    def _frame_point(self, event):
        """The event's position in frame fractions, inside the frame."""
        scene_point = self.mapToScene(event.position().toPoint())
        frame_width, frame_height = self.frame_size()

        return (
            min(max(scene_point.x() / frame_width, 0.0), 1.0),
            min(max(scene_point.y() / frame_height, 0.0), 1.0),
        )

    def _grab_tolerance(self):
        """The grab distance (view pixels) in frame fractions at the
        current zoom."""
        scene_px = LIVE_HISTOGRAM_REGION_GRAB_PX / max(self.transform().m11(), 1e-9)
        frame_width, frame_height = self.frame_size()

        return scene_px / frame_width, scene_px / frame_height

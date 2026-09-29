# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# image_viewer/analysis/roi_items.py
"""The ROI shape items drawn on the image canvas. Each carries its
angle as a Qt item rotation about its own centre, which keeps every
grip position and resize computation in unrotated local coordinates,
and reports its geometry back through the layer's edit callback."""

# Standard library imports.
import math

# Third-party imports.
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QPainterPath, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsSimpleTextItem,
)

# Local imports.
from .consts import MIN_ROI_SIZE_PX
from .roi_geometry import centre_of, normalize
from .roi_handles import (
    BALL_REFERENCE_PEN,
    HANDLE_SIZE_PX,
    ROI_PEN,
    ROI_SELECTED_PEN,
    CornerRadiusHandle,
    NodeHandle,
    ResizeHandle,
    RotateHandle,
)


class _RoiItemBase:
    """Shared behavior mixed into the two shape items: identity, label,
    grip, edit-mode flags, and commit-on-release."""

    #: True while the user drags this item (a move) or its resize
    #: handle: sync() skips this item while it's set, so it doesn't
    #: yank a rect the user is actively dragging.
    _dragging = False

    def _setup(self, roi_id, name, on_edited):
        self.roi_id = roi_id
        self._on_edited = on_edited
        self.setPen(ROI_PEN)
        self._label = QGraphicsSimpleTextItem(name, self)
        self._label.setBrush(QBrush(ROI_PEN.color()))
        self._label.setFlag(self._label.GraphicsItemFlag.ItemIgnoresTransformations)
        self._handle = ResizeHandle(self)
        self._rotate_handle = RotateHandle(self)

    def set_editable(self, editable):
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, editable)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, editable)
        self._handle.setVisible(editable)
        self._rotate_handle.setVisible(editable)

    def angle_to(self, scene_point):
        """Degrees clockwise from the shape's centre to a scene point."""
        centre = self.mapToScene(self.transformOriginPoint())
        return math.degrees(
            math.atan2(scene_point.y() - centre.y(), scene_point.x() - centre.x())
        )

    def set_angle(self, degrees):
        self.setRotation(degrees)

    def resize_to(self, scene_point, uniform=False):
        # mapFromScene undoes the item's rotation, so every shape sizes
        # itself in the unrotated frame it was authored in.
        self._apply_size(self.mapFromScene(scene_point), uniform)
        self._place_attachments()

    def _place_grips(self, centre_x, centre_y, half_width, half_height):
        """Resize grip at the local bottom-right, rotate grip at the
        top-left, label clear of both. All three ignore inherited
        transformations, so they stay upright while their positions
        still ride the rotation."""
        self._handle.setPos(centre_x + half_width, centre_y + half_height)
        self._rotate_handle.setPos(centre_x - half_width, centre_y - half_height)
        self._label.setPos(
            centre_x - half_width + HANDLE_SIZE_PX, centre_y - half_height - 2
        )

    def set_name(self, name):
        self._label.setText(name)

    def set_selected_style(self, selected):
        self.setPen(ROI_SELECTED_PEN if selected else ROI_PEN)
        self._label.setBrush(QBrush(self.pen().color()))

    def is_dragging(self):
        return self._dragging

    def commit_geometry(self):
        self._on_edited(self.roi_id, self.geometry())

    def mousePressEvent(self, event):
        # Starts a possible move drag: guard sync() until release.
        super().mousePressEvent(event)
        if self.flags() & self.GraphicsItemFlag.ItemIsMovable:
            self._dragging = True

    def mouseReleaseEvent(self, event):
        # Ends a move drag: report the moved geometry, then let sync()
        # touch this item again.
        super().mouseReleaseEvent(event)
        if self.flags() & self.GraphicsItemFlag.ItemIsMovable:
            self.commit_geometry()
        self._dragging = False


def capsule_path(geometry):
    """The stadium QPainterPath for a canonical capsule geometry, in
    unrotated local coordinates (the item transform adds the angle)."""
    _, values = normalize("capsule", geometry)
    centre_x, centre_y, half_length, radius, _angle = values
    rectangle = QRectF(
        centre_x - half_length - radius,
        centre_y - radius,
        2 * (half_length + radius),
        2 * radius,
    )
    path = QPainterPath()
    path.addRoundedRect(rectangle, radius, radius)
    return path


class EllipseRoiItem(_RoiItemBase, QGraphicsEllipseItem):
    """Ellipse ROI: geometry [cx, cy, rx, ry, angle]; a circle is
    simply rx == ry."""

    def __init__(self, roi_id, name, geometry, on_edited):
        QGraphicsEllipseItem.__init__(self)
        self._setup(roi_id, name, on_edited)
        self.set_geometry(geometry)

    def set_geometry(self, geometry):
        _, values = normalize("ellipse", geometry)
        centre_x, centre_y, radius_x, radius_y, angle = values
        self.setPos(0, 0)
        self.setRect(
            centre_x - radius_x, centre_y - radius_y, 2 * radius_x, 2 * radius_y
        )
        self.setTransformOriginPoint(centre_x, centre_y)
        self.setRotation(angle)
        self._place_attachments()

    def geometry(self):
        rect = self.rect()
        centre = rect.center() + self.pos()
        return [
            centre.x(),
            centre.y(),
            rect.width() / 2,
            rect.height() / 2,
            self.rotation(),
        ]

    def _apply_size(self, point, uniform):
        centre = self.rect().center()
        radius_x = max(abs(point.x() - centre.x()), MIN_ROI_SIZE_PX)
        radius_y = max(abs(point.y() - centre.y()), MIN_ROI_SIZE_PX)
        if uniform:
            radius_x = radius_y = max(radius_x, radius_y)
        self.setRect(
            centre.x() - radius_x, centre.y() - radius_y, 2 * radius_x, 2 * radius_y
        )

    def _place_attachments(self):
        rect = self.rect()
        self._place_grips(
            rect.center().x(), rect.center().y(), rect.width() / 2, rect.height() / 2
        )


def box_path(geometry):
    """The (possibly rounded) box QPainterPath in unrotated local
    coordinates — the item transform adds the angle."""
    _, values = normalize("box", geometry)
    x, y, width, height, _angle, corner_radius = values
    path = QPainterPath()
    rectangle = QRectF(x, y, width, height)
    if corner_radius > 0.0:
        path.addRoundedRect(rectangle, corner_radius, corner_radius)
    else:
        path.addRect(rectangle)
    return path


class BallReferenceItem(EllipseRoiItem):
    """The rolling ball drawn at its true size, as a guide.

    It is not an ROI: nothing is measured inside it and it is never
    saved. It looks like one so that it can be judged against them —
    the whole point is to see whether the ball clears the droplets —
    but it carries its own colour and stays a circle, a ball having
    only one radius."""

    def __init__(self, roi_id, name, geometry, on_edited):
        super().__init__(roi_id, name, geometry, on_edited)
        self.setPen(BALL_REFERENCE_PEN)
        self._label.setBrush(QBrush(BALL_REFERENCE_PEN.color()))
        # A circle has nothing to rotate.
        self._rotate_handle.setVisible(False)

    def _apply_size(self, point, uniform):
        # Always uniform, whatever the modifier: dragging this to an
        # ellipse would describe a ball that cannot exist.
        super()._apply_size(point, True)

    def set_selected_style(self, selected):
        # Its colour says what it is; selection must not repaint it as
        # an ROI.
        self._label.setBrush(QBrush(self.pen().color()))

    def set_editable(self, editable):
        super().set_editable(editable)
        self._rotate_handle.setVisible(False)


class BoxRoiItem(_RoiItemBase, QGraphicsPathItem):
    """Box ROI: geometry [x, y, width, height, angle, corner_radius]
    with (x, y) the unrotated top-left corner; it rotates about its
    centre. A path item rather than a rect one so the corners can
    round."""

    def __init__(self, roi_id, name, geometry, on_edited):
        QGraphicsPathItem.__init__(self)
        self._rect = QRectF(0, 0, MIN_ROI_SIZE_PX, MIN_ROI_SIZE_PX)
        self._corner_radius = 0.0
        self._setup(roi_id, name, on_edited)
        self._radius_handle = CornerRadiusHandle(self)
        self._radius_handle.setVisible(False)
        self.set_geometry(geometry)

    def set_geometry(self, geometry):
        _, values = normalize("box", geometry)
        x, y, width, height, angle, self._corner_radius = values
        self._rect = QRectF(x, y, width, height)
        self.setPos(0, 0)
        self.setPath(box_path(values))
        self.setTransformOriginPoint(*centre_of("box", values))
        self.setRotation(angle)
        self._place_attachments()

    def geometry(self):
        return [
            self._rect.x() + self.pos().x(),
            self._rect.y() + self.pos().y(),
            self._rect.width(),
            self._rect.height(),
            self.rotation(),
            self._corner_radius,
        ]

    def set_editable(self, editable):
        super().set_editable(editable)
        self._radius_handle.setVisible(editable)

    def round_to(self, scene_point):
        """Radius from how far the grip was dragged in along the top
        edge, in the unrotated frame the shape was authored in."""
        point = self.mapFromScene(scene_point)
        self._corner_radius = max(self._rect.right() - point.x(), 0.0)
        self._redraw()
        self._place_attachments()

    def _apply_size(self, point, uniform):
        # Centre-anchored, unlike the pre-rotation top-left anchoring:
        # a moving centre would drag the rotation pivot mid-drag.
        centre = self._rect.center()
        half_width = max(abs(point.x() - centre.x()), MIN_ROI_SIZE_PX)
        half_height = max(abs(point.y() - centre.y()), MIN_ROI_SIZE_PX)
        self._rect = QRectF(
            centre.x() - half_width,
            centre.y() - half_height,
            2 * half_width,
            2 * half_height,
        )
        self._redraw()

    def _redraw(self):
        """Rebuild the path from the current rect and radius, clamping
        the radius the way normalize() would (a resize can shrink the
        box under a radius it already carries). Local coordinates
        throughout: the item's own pos() offsets the result."""
        _, values = normalize(
            "box",
            [
                self._rect.x(),
                self._rect.y(),
                self._rect.width(),
                self._rect.height(),
                self.rotation(),
                self._corner_radius,
            ],
        )
        self._corner_radius = values[5]
        self.setPath(box_path(values))

    def _place_attachments(self):
        rect = self._rect
        self._place_grips(
            rect.center().x(), rect.center().y(), rect.width() / 2, rect.height() / 2
        )
        self._radius_handle.setPos(rect.right() - self._corner_radius, rect.top())


class CapsuleRoiItem(_RoiItemBase, QGraphicsPathItem):
    """Capsule (spherocylinder) ROI: geometry
    [cx, cy, half_length, radius, angle]."""

    def __init__(self, roi_id, name, geometry, on_edited):
        QGraphicsPathItem.__init__(self)
        self._centre_x = 0.0
        self._centre_y = 0.0
        self._half_length = MIN_ROI_SIZE_PX
        self._radius = MIN_ROI_SIZE_PX
        self._setup(roi_id, name, on_edited)
        self.set_geometry(geometry)

    def set_geometry(self, geometry):
        _, values = normalize("capsule", geometry)
        (self._centre_x, self._centre_y, self._half_length, self._radius, angle) = (
            values
        )
        self.setPos(0, 0)
        self.setPath(capsule_path(values))
        self.setTransformOriginPoint(self._centre_x, self._centre_y)
        self.setRotation(angle)
        self._place_attachments()

    def geometry(self):
        return [
            self._centre_x + self.pos().x(),
            self._centre_y + self.pos().y(),
            self._half_length,
            self._radius,
            self.rotation(),
        ]

    def _apply_size(self, point, uniform):
        # The grip rides the bounding corner, so its x distance covers
        # the cap radius as well as the straight half-length.
        self._radius = max(abs(point.y() - self._centre_y), MIN_ROI_SIZE_PX)
        self._half_length = max(
            abs(point.x() - self._centre_x) - self._radius, MIN_ROI_SIZE_PX
        )
        self.setPath(
            capsule_path(
                [self._centre_x, self._centre_y, self._half_length, self._radius, 0.0]
            )
        )

    def _place_attachments(self):
        self._place_grips(
            self._centre_x,
            self._centre_y,
            self._half_length + self._radius,
            self._radius,
        )


class PolygonRoiItem(_RoiItemBase, QGraphicsPolygonItem):
    """Contour ROI: geometry is the flat vertex list
    [x1, y1, x2, y2, ...], with any rotation already applied to the
    coordinates. One node grip per vertex, shown while selected."""

    def __init__(self, roi_id, name, geometry, on_edited):
        QGraphicsPolygonItem.__init__(self)
        self._node_handles = []
        self._selected = False
        self._editable = False
        self._setup(roi_id, name, on_edited)
        self.set_geometry(geometry)

    def set_geometry(self, geometry):
        _, values = normalize("polygon", geometry)
        points = [
            QPointF(values[index], values[index + 1])
            for index in range(0, len(values), 2)
        ]
        self.setPos(0, 0)
        self.setRotation(0)  # a stored contour is already oriented
        self.setPolygon(QPolygonF(points))
        self.setTransformOriginPoint(*centre_of("polygon", values))
        self._rebuild_node_handles()
        self._place_attachments()

    def geometry(self):
        # Through the item transform, so a move or a live rotation
        # lands in the coordinates and never needs storing as an angle.
        return [
            value
            for point in self.polygon()
            for value in (self.mapToScene(point).x(), self.mapToScene(point).y())
        ]

    def move_node(self, index, scene_point):
        points = list(self.polygon())
        points[index] = self.mapFromScene(scene_point)
        self.setPolygon(QPolygonF(points))
        self._node_handles[index].setPos(points[index])
        self._place_attachments()

    def set_editable(self, editable):
        super().set_editable(editable)
        self._editable = editable
        # Contours are shaped by their nodes, so the resize grip stays
        # hidden (a hidden item receives no mouse events).
        self._handle.setVisible(False)
        self._update_node_visibility()

    def set_selected_style(self, selected):
        super().set_selected_style(selected)
        self._selected = selected
        self._update_node_visibility()

    def _update_node_visibility(self):
        for handle in self._node_handles:
            handle.setVisible(self._selected and self._editable)

    def _rebuild_node_handles(self):
        for handle in self._node_handles:
            handle.setParentItem(None)
        self._node_handles = []
        for index, point in enumerate(self.polygon()):
            handle = NodeHandle(self, index)
            handle.setPos(point)
            self._node_handles.append(handle)
        self._update_node_visibility()

    def _apply_size(self, point, uniform):
        """No-op: the resize grip is hidden for contours."""

    def _place_attachments(self):
        bounds = self.polygon().boundingRect()
        self._place_grips(
            bounds.center().x(),
            bounds.center().y(),
            bounds.width() / 2,
            bounds.height() / 2,
        )

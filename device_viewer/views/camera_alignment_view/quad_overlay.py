"""The endpoint-style editable quad: an orange frame with four
conspicuous corner dots — deliberately distinct from the regular
camera aligner's thin red reference rect, so the user always knows
which of the two they are looking at.

Used in two places: the start-point picker dialog (over the captured
camera frame, in camera-pixel coordinates) and the endpoint
viewer/adjuster (over the device scene, in scene coordinates)."""

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsPolygonItem

# The endpoint look (defaults — each overlay can be restyled live):
# orange frame, deeper-orange dots with a white ring so they stay
# conspicuous over any feed. ALIGNMENT_SNAP_RADIUS_PX is the distance
# (in VIEW pixels, zoom-aware like the handles themselves) within
# which a dragged handle snaps onto a snap point.
from ...consts import (
    ALIGNMENT_FRAME_WIDTH_PX,
    ALIGNMENT_HANDLE_COLOR_HEX,
    ALIGNMENT_HANDLE_RADIUS_PX,
    ALIGNMENT_HANDLE_RING_COLOR_HEX,
    ALIGNMENT_QUAD_COLOR_HEX,
    ALIGNMENT_SNAP_MARKER_ALPHA,
    ALIGNMENT_SNAP_MARKER_COLOR_HEX,
    ALIGNMENT_SNAP_MARKER_SIZE_PX,
    ALIGNMENT_SNAP_RADIUS_PX,
)


class SnapPointMarkersItem(QGraphicsItem):
    """Every snappable corner as a small fixed-size dot. One item
    paints them all through a single cosmetic pen (dot size stays in
    VIEW pixels at any zoom) — hundreds of separate QGraphicsItems
    would bog the scene down."""

    def __init__(self, points, color, alpha, marker_px=ALIGNMENT_SNAP_MARKER_SIZE_PX):
        super().__init__()
        self._marker_px = marker_px
        self._polygon = QPolygonF()

        self._pen = QPen()
        self._pen.setCosmetic(True)
        self._pen.setWidthF(marker_px)
        self._pen.setCapStyle(Qt.RoundCap)

        self.set_style(color=color, alpha=alpha)
        self.set_points(points)

    def set_points(self, points):
        self.prepareGeometryChange()
        self._polygon = QPolygonF([QPointF(float(x), float(y)) for x, y in points])
        self.update()

    def set_style(self, color=None, alpha=None):
        """Restyle the dots; None leaves that aspect as-is."""
        pen_color = self._pen.color() if color is None else QColor(color)
        pen_color.setAlphaF(
            self._pen.color().alphaF() if alpha is None else float(alpha)
        )
        self._pen.setColor(pen_color)
        self.update()

    def boundingRect(self):
        # The cosmetic-pen dots extend past the points in VIEW
        # pixels; pad generously so they aren't clipped when the
        # view is zoomed far out.
        margin = self._marker_px * 10
        return self._polygon.boundingRect().adjusted(-margin, -margin, margin, margin)

    def paint(self, painter, option, widget=None):
        painter.setPen(self._pen)
        painter.drawPoints(self._polygon)


class QuadHandleItem(QGraphicsEllipseItem):
    """One draggable corner dot. Ignores the view transform so the
    dot stays the same conspicuous size at any zoom."""

    def __init__(
        self,
        on_moved,
        on_released,
        parent=None,
        radius=ALIGNMENT_HANDLE_RADIUS_PX,
        color=ALIGNMENT_HANDLE_COLOR_HEX,
        ring_color=ALIGNMENT_HANDLE_RING_COLOR_HEX,
    ):
        super().__init__(-radius, -radius, 2 * radius, 2 * radius, parent)
        self._on_moved = on_moved
        self._on_released = on_released
        #: Optional QPointF -> QPointF hook applied while dragging.
        self.snap_fn = None
        self.setBrush(QBrush(QColor(color)))
        self.setPen(QPen(QColor(ring_color), 2))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setCursor(Qt.OpenHandCursor)

    def set_radius(self, radius):
        self.setRect(-radius, -radius, 2 * radius, 2 * radius)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.snap_fn is not None:
            return self.snap_fn(value)
        if (
            change == QGraphicsItem.ItemScenePositionHasChanged
            and self._on_moved is not None
        ):
            self._on_moved()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._on_released is not None:
            self._on_released()


class QuadOverlay:
    """The orange frame plus its four corner handles, managed as one
    unit on a QGraphicsScene."""

    def __init__(
        self,
        scene,
        quad,
        on_changed=None,
        on_released=None,
        z_value=50.0,
        snap_points=None,
        snap_radius_px=ALIGNMENT_SNAP_RADIUS_PX,
        handle_radius_px=ALIGNMENT_HANDLE_RADIUS_PX,
        frame_width_px=ALIGNMENT_FRAME_WIDTH_PX,
        quad_color=ALIGNMENT_QUAD_COLOR_HEX,
        handle_color=ALIGNMENT_HANDLE_COLOR_HEX,
        handle_ring_color=ALIGNMENT_HANDLE_RING_COLOR_HEX,
        snap_marker_color=ALIGNMENT_SNAP_MARKER_COLOR_HEX,
        snap_marker_alpha=ALIGNMENT_SNAP_MARKER_ALPHA,
    ):
        """``quad``: four (x, y) scene points, TL/TR/BR/BL.
        ``on_changed`` fires on every handle drag step (with the
        current quad); ``on_released`` when a drag ends.
        ``snap_points``: optional (x, y) scene points (e.g. device
        corner vertices) that dragged handles snap onto when within
        ``snap_radius_px`` view pixels. Colors accept anything
        QColor does (QColor or '#rrggbb')."""
        self._scene = scene
        self._on_changed = on_changed
        self._on_released = on_released
        self._syncing = False
        self._snap_radius_px = float(snap_radius_px)
        self._snap_points = (
            np.asarray(snap_points, dtype=float)
            if snap_points is not None and len(snap_points)
            else None
        )

        # View-all-corners markers, created lazily on first show.
        self._snap_markers = None
        self._snap_marker_color = snap_marker_color
        self._snap_marker_alpha = float(snap_marker_alpha)
        self._z_value = z_value

        self._frame = QGraphicsPolygonItem()
        pen = QPen(QColor(quad_color), frame_width_px)
        pen.setCosmetic(True)  # constant width at any zoom
        self._frame.setPen(pen)
        self._frame.setZValue(z_value)
        scene.addItem(self._frame)

        self._handles = []
        for _ in range(4):
            handle = QuadHandleItem(
                self._handle_moved,
                self._handle_released,
                radius=handle_radius_px,
                color=handle_color,
                ring_color=handle_ring_color,
            )
            if self._snap_points is not None:
                handle.snap_fn = self._snap
            handle.setZValue(z_value + 1)
            scene.addItem(handle)
            self._handles.append(handle)
        self.set_quad(quad)

    # ------------------------------------------------------------------ #
    def quad(self) -> list:
        """The current corner positions as [[x, y] * 4]."""
        return [[handle.pos().x(), handle.pos().y()] for handle in self._handles]

    def set_quad(self, quad):
        self._syncing = True
        try:
            for handle, point in zip(self._handles, quad):
                handle.setPos(QPointF(float(point[0]), float(point[1])))
        finally:
            self._syncing = False
        self._sync_frame()

    def set_editable(self, editable: bool):
        for handle in self._handles:
            handle.setFlag(QGraphicsItem.ItemIsMovable, bool(editable))

    def set_snap_radius(self, snap_radius_px):
        self._snap_radius_px = float(snap_radius_px)

    def set_snap_points(self, snap_points):
        """Replace the snap targets (e.g. after recapturing the
        camera frame); None or empty disables snapping."""
        self._snap_points = (
            np.asarray(snap_points, dtype=float)
            if snap_points is not None and len(snap_points)
            else None
        )
        snap_fn = self._snap if self._snap_points is not None else None
        for handle in self._handles:
            handle.snap_fn = snap_fn

        if self._snap_markers is not None:
            if self._snap_points is None:
                self._scene.removeItem(self._snap_markers)
                self._snap_markers = None
            else:
                self._snap_markers.set_points(self._snap_points)

    def set_snap_markers_visible(self, visible):
        """Show/hide every snap point as a dot (view-all-corners)."""
        if visible and self._snap_markers is None and self._snap_points is not None:
            markers = SnapPointMarkersItem(
                self._snap_points, self._snap_marker_color, self._snap_marker_alpha
            )
            markers.setZValue(self._z_value - 1)
            self._scene.addItem(markers)
            self._snap_markers = markers
        if self._snap_markers is not None:
            self._snap_markers.setVisible(bool(visible))

    def set_appearance(
        self,
        handle_radius_px=None,
        frame_width_px=None,
        quad_color=None,
        handle_color=None,
        handle_ring_color=None,
        snap_marker_color=None,
        snap_marker_alpha=None,
    ):
        """Restyle the overlay live; None leaves that aspect as-is."""
        if snap_marker_color is not None:
            self._snap_marker_color = snap_marker_color
        if snap_marker_alpha is not None:
            self._snap_marker_alpha = float(snap_marker_alpha)
        if self._snap_markers is not None and (
            snap_marker_color is not None or snap_marker_alpha is not None
        ):
            self._snap_markers.set_style(
                color=snap_marker_color, alpha=snap_marker_alpha
            )
        if handle_radius_px is not None:
            for handle in self._handles:
                handle.set_radius(handle_radius_px)
        pen = self._frame.pen()
        if frame_width_px is not None:
            pen.setWidthF(float(frame_width_px))
        if quad_color is not None:
            pen.setColor(QColor(quad_color))
        self._frame.setPen(pen)
        if handle_color is not None:
            for handle in self._handles:
                handle.setBrush(QBrush(QColor(handle_color)))
        if handle_ring_color is not None:
            for handle in self._handles:
                ring_pen = handle.pen()
                ring_pen.setColor(QColor(handle_ring_color))
                handle.setPen(ring_pen)

    def remove(self):
        """Take the overlay off its scene."""
        for handle in self._handles:
            self._scene.removeItem(handle)
        self._scene.removeItem(self._frame)
        if self._snap_markers is not None:
            self._scene.removeItem(self._snap_markers)
            self._snap_markers = None
        self._handles = []

    # ------------------------------------------------------------------ #
    def _snap(self, pos):
        """The nearest snap point when it is within the snap radius
        (view pixels) of ``pos``, else ``pos`` unchanged.
        Programmatic set_quad placements are never snapped."""
        if self._syncing:
            return pos
        deltas = self._snap_points - [pos.x(), pos.y()]
        nearest = int(np.argmin((deltas * deltas).sum(axis=1)))
        # Zoom-awareness assumes the scene has exactly one view (true
        # for the alignment panes, which each own their scene) — with
        # several views this would use the first one's zoom for all.
        views = self._scene.views()
        scale = views[0].transform().m11() if views else 1.0
        if np.hypot(*deltas[nearest]) * scale <= self._snap_radius_px:
            return QPointF(*self._snap_points[nearest])
        return pos

    def _sync_frame(self):
        self._frame.setPolygon(QPolygonF([handle.pos() for handle in self._handles]))

    def _handle_moved(self):
        if self._syncing:
            return
        self._sync_frame()
        if self._on_changed is not None:
            self._on_changed(self.quad())

    def _handle_released(self):
        if self._on_released is not None:
            self._on_released(self.quad())

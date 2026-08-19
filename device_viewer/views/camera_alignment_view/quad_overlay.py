"""The endpoint-style editable quad: an orange frame with four
conspicuous corner dots — deliberately distinct from the regular
camera aligner's thin red reference rect, so the user always knows
which of the two they are looking at.

Used in two places: the start-point picker dialog (over the captured
camera frame, in camera-pixel coordinates) and the endpoint
viewer/adjuster (over the device scene, in scene coordinates)."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, \
    QGraphicsPolygonItem

#: The endpoint look: orange frame, deeper-orange dots with a white
#: ring so they stay conspicuous over any feed.
QUAD_COLOR = QColor(255, 160, 0)
HANDLE_COLOR = QColor(255, 100, 0)
HANDLE_RING_COLOR = QColor(255, 255, 255)
HANDLE_RADIUS_PX = 8
FRAME_WIDTH_PX = 3


class QuadHandleItem(QGraphicsEllipseItem):
    """One draggable corner dot. Ignores the view transform so the
    dot stays the same conspicuous size at any zoom."""

    def __init__(self, on_moved, on_released, parent=None):
        radius = HANDLE_RADIUS_PX
        super().__init__(-radius, -radius, 2 * radius, 2 * radius,
                         parent)
        self._on_moved = on_moved
        self._on_released = on_released
        self.setBrush(QBrush(HANDLE_COLOR))
        self.setPen(QPen(HANDLE_RING_COLOR, 2))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges,
                     True)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setCursor(Qt.OpenHandCursor)

    def itemChange(self, change, value):
        if (change
                == QGraphicsItem.ItemScenePositionHasChanged
                and self._on_moved is not None):
            self._on_moved()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._on_released is not None:
            self._on_released()


class QuadOverlay:
    """The orange frame plus its four corner handles, managed as one
    unit on a QGraphicsScene."""

    def __init__(self, scene, quad, on_changed=None,
                 on_released=None, z_value=50.0):
        """``quad``: four (x, y) scene points, TL/TR/BR/BL.
        ``on_changed`` fires on every handle drag step (with the
        current quad); ``on_released`` when a drag ends."""
        self._scene = scene
        self._on_changed = on_changed
        self._on_released = on_released
        self._syncing = False

        self._frame = QGraphicsPolygonItem()
        pen = QPen(QUAD_COLOR, FRAME_WIDTH_PX)
        pen.setCosmetic(True)  # constant width at any zoom
        self._frame.setPen(pen)
        self._frame.setZValue(z_value)
        scene.addItem(self._frame)

        self._handles = []
        for _ in range(4):
            handle = QuadHandleItem(self._handle_moved,
                                    self._handle_released)
            handle.setZValue(z_value + 1)
            scene.addItem(handle)
            self._handles.append(handle)
        self.set_quad(quad)

    # ------------------------------------------------------------------ #
    def quad(self) -> list:
        """The current corner positions as [[x, y] * 4]."""
        return [[handle.pos().x(), handle.pos().y()]
                for handle in self._handles]

    def set_quad(self, quad):
        self._syncing = True
        try:
            for handle, point in zip(self._handles, quad):
                handle.setPos(QPointF(float(point[0]),
                                      float(point[1])))
        finally:
            self._syncing = False
        self._sync_frame()

    def set_editable(self, editable: bool):
        for handle in self._handles:
            handle.setFlag(QGraphicsItem.ItemIsMovable,
                           bool(editable))

    def remove(self):
        """Take the overlay off its scene."""
        for handle in self._handles:
            self._scene.removeItem(handle)
        self._scene.removeItem(self._frame)
        self._handles = []

    # ------------------------------------------------------------------ #
    def _sync_frame(self):
        self._frame.setPolygon(QPolygonF(
            [handle.pos() for handle in self._handles]))

    def _handle_moved(self):
        if self._syncing:
            return
        self._sync_frame()
        if self._on_changed is not None:
            self._on_changed(self.quad())

    def _handle_released(self):
        if self._on_released is not None:
            self._on_released(self.quad())

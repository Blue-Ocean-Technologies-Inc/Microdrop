"""The zoomable image canvas shared by the camera-alignment panels
(the outline picker over a captured camera frame, and the endpoint
editor over the rendered device SVG): scene coordinates ARE image
pixels, the wheel zooms about the cursor, and dragging anywhere off
a corner dot pans."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from .quad_overlay import QuadHandleItem

#: Wheel-zoom limits (view scale factors).
ZOOM_MIN = 0.1
ZOOM_MAX = 40.0
ZOOM_STEP = 1.25


class ZoomPanImageView(QGraphicsView):

    def __init__(self, pixmap, parent=None):
        # The view does not own its scene — keep a reference.
        self._scene = QGraphicsScene()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        super().__init__(self._scene, parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self._zoom = 1.0
        self._fitted_once = False

    def wheelEvent(self, event):
        factor = ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / ZOOM_STEP
        target = self._zoom * factor
        if not ZOOM_MIN <= target <= ZOOM_MAX:
            return
        self._zoom = target
        self.scale(factor, factor)

    def set_pixmap(self, pixmap):
        """Swap the displayed image (frame recapture). The scene
        rect follows the new size; zoom/pan are left alone so a
        same-resolution recapture keeps the user's framing."""
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

    def fit_frame(self):
        self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def showEvent(self, event):
        # Fit the frame on the FIRST show only — re-shows (window
        # minimized/restored) keep the user's zoom and pan.
        super().showEvent(event)
        if not self._fitted_once:
            self._fitted_once = True
            self.fit_frame()

    def mousePressEvent(self, event):
        # A press on a corner dot drags the dot; anywhere else pans.
        position = event.position().toPoint()
        if not isinstance(self.itemAt(position), QuadHandleItem):
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setDragMode(QGraphicsView.NoDrag)

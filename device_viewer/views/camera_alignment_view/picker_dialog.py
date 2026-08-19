"""Manual device-outline picker for camera alignment.

A popup showing ONE captured camera frame — just the device image,
none of the device viewer's overlays in the way — where the user
drags the four conspicuous corner dots of an orange quad onto the
device outline themselves. The panel is zoomable (scroll to zoom
about the cursor, drag the background to pan) so corners can be
placed to the pixel. "Use These Points" hands the quad back in
CAMERA pixels to be staged on the feed for 'Go To Endpoint'.

Deliberately no auto-detection: the user IS the detector here."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

from logger.logger_service import get_logger

from .quad_overlay import QuadHandleItem, QuadOverlay

logger = get_logger(__name__)

#: The dialog opens sized so the frame fits inside this box.
VIEW_START_WIDTH_PX = 1100
VIEW_START_HEIGHT_PX = 750
#: Wheel-zoom limits (view scale factors).
ZOOM_MIN = 0.1
ZOOM_MAX = 40.0
ZOOM_STEP = 1.25


class _PickerView(QGraphicsView):
    """The zoomable frame canvas: scene coordinates ARE camera
    pixels, the wheel zooms about the cursor, and dragging anywhere
    off a corner dot pans."""

    def __init__(self, pixmap, parent=None):
        # The view does not own its scene — keep a reference.
        self._scene = QGraphicsScene()
        self._scene.addPixmap(pixmap)
        super().__init__(self._scene, parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self._zoom = 1.0

    def wheelEvent(self, event):
        factor = ZOOM_STEP if event.angleDelta().y() > 0 \
            else 1.0 / ZOOM_STEP
        target = self._zoom * factor
        if not ZOOM_MIN <= target <= ZOOM_MAX:
            return
        self._zoom = target
        self.scale(factor, factor)

    def fit_frame(self):
        self.fitInView(self.scene().sceneRect(),
                       Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def mousePressEvent(self, event):
        # A press on a corner dot drags the dot; anywhere else pans.
        position = event.position().toPoint()
        if not isinstance(self.itemAt(position), QuadHandleItem):
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setDragMode(QGraphicsView.NoDrag)


class AlignmentPickerDialog(QDialog):
    """Pick the device outline on a captured frame, by hand."""

    #: Emitted on accept with the quad in CAMERA pixels
    #: ([[x, y] * 4], TL/TR/BR/BL as placed).
    quad_accepted = Signal(list)

    def __init__(self, frame_image: QImage, initial_quad=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Device Outline")
        pixmap = QPixmap.fromImage(frame_image)
        self._view = _PickerView(pixmap)

        quad = initial_quad if initial_quad \
            and len(initial_quad) == 4 \
            else self._default_quad(pixmap)
        self._overlay = QuadOverlay(self._view.scene(), quad)

        status = QLabel(
            "Drag the four corner dots onto the device's corners. "
            "Scroll to zoom, drag the image to pan.")
        status.setWordWrap(True)

        fit_button = QPushButton("Fit View")
        fit_button.clicked.connect(self._view.fit_frame)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        accept_button = QPushButton("Use These Points")
        accept_button.setDefault(True)
        accept_button.clicked.connect(self._on_accept)

        buttons = QHBoxLayout()
        buttons.addWidget(fit_button)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(accept_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self._view)
        layout.addWidget(status)
        layout.addLayout(buttons)

        scale = min(VIEW_START_WIDTH_PX / max(pixmap.width(), 1),
                    VIEW_START_HEIGHT_PX / max(pixmap.height(), 1),
                    1.0)
        self._view.setMinimumSize(320, 240)
        self.resize(int(pixmap.width() * scale) + 40,
                    int(pixmap.height() * scale) + 110)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _default_quad(pixmap) -> list:
        """A centered half-frame box to start from when no previous
        alignment maps onto this frame."""
        width, height = pixmap.width(), pixmap.height()
        return [[width * 0.25, height * 0.25],
                [width * 0.75, height * 0.25],
                [width * 0.75, height * 0.75],
                [width * 0.25, height * 0.75]]

    def showEvent(self, event):
        super().showEvent(event)
        self._view.fit_frame()

    def _on_accept(self):
        self.quad_accepted.emit(self._overlay.quad())
        self.accept()

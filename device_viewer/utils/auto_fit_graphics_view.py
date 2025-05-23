from pyface.qt.QtWidgets import QGraphicsView
from pyface.qt.QtCore import Qt

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class AutoFitGraphicsView(QGraphicsView):
    """
    A QGraphicsView that automatically fits the scene rect when the view is resized
    """

    def resizeEvent(self, event):
        logger.debug(f"Resizing view size: {self.scene().sceneRect()}")
        self.fitInView(self.scene().sceneRect().adjusted(20, 20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)
        super().resizeEvent(event)
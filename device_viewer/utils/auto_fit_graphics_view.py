from pyface.qt.QtWidgets import QGraphicsView
from pyface.qt.QtCore import Qt, Signal
from pyface.qt.QtGui import QPainter

from logger.logger_service import get_logger

logger = get_logger(__name__)


class AutoFitGraphicsView(QGraphicsView):
    """
    A QGraphicsView with a method to fit to scene size.
    """
    display_state_signal = Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)

    def fit_to_scene_rect(self):
        if self.scene():
            self.fitInView(self.scene().sceneRect().adjusted(20, 20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)
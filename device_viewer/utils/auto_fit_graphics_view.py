from pyface.qt.QtWidgets import QGraphicsView
from pyface.qt.QtCore import Qt, Signal
from pyface.qt.QtGui import QPainter

from device_viewer.consts import AUTO_FIT_MARGIN_SCALE
from logger.logger_service import get_logger

logger = get_logger(__name__)


class AutoFitGraphicsView(QGraphicsView):
    """
    A QGraphicsView with a method to fit to scene size.
    """
    display_state_signal = Signal(str)

    def __init__(self, *args, **kwargs):

        # check initial auto fit value
        self.auto_fit = kwargs.pop('auto_fit', True)
        self.auto_fit_margin_scale = kwargs.pop('auto_fit_margin_scale', AUTO_FIT_MARGIN_SCALE)

        super().__init__(*args, **kwargs)
        
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)

    def resizeEvent(self, event):
        if self.auto_fit:
            self.fit_to_scene_rect()

        super().resizeEvent(event)

    def fit_to_scene_rect(self):
        if self.scene():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        # scale down to leave margin
        self.scale(self.auto_fit_margin_scale, self.auto_fit_margin_scale)
from PySide6.QtCore import QPointF
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneContextMenuEvent

from logger.logger_service import get_logger
from ...services.electrode_interaction_service import ElectrodeInteractionControllerService

logger = get_logger(__name__, level='DEBUG')

class ElectrodeScene(QGraphicsScene):
    """
    Class to handle electrode view scene using elements contained in the electrode layer.
    Handles identifying mouse action across the scene.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._interaction_service: 'ElectrodeInteractionControllerService' = None

    @property
    def interaction_service(self):
        #: The service handling electrode interactions
        return self._interaction_service

    @interaction_service.setter
    def interaction_service(self, interaction_service: ElectrodeInteractionControllerService):
        self._interaction_service = interaction_service

    def get_item_under_mouse(self, coordinates: QPointF, object_type):
        '''
        Searches for an object with type object_type in the scene at coordinates. This will be able to find items at lower z indexes. 
        '''
        # Because QGraphicsScene is so primitive, we need to manually get item under the mouse click via coordinates since we can't use signals (QGraphicsItem is not a QObject)
        # Event bubbling (using the mousePressEvent from the ElectrodeView) has some strange behaviour, so this approach is used instead
        items = self.items(coordinates, deviceTransform=self.views()[0].transform())
        for item in items:
            if isinstance(item, object_type):
                return item
        return None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self.interaction_service.handle_key_press_event(event)
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Handle the start of a mouse click event."""
        self.interaction_service.handle_mouse_press_event(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle the dragging motion."""
        self.interaction_service.handle_mouse_move_event(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finalize the drag operation."""
        self.interaction_service.handle_mouse_release_event(event)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if not self.interaction_service.handle_scene_wheel_event(event):
            super().wheelEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent):
        self.interaction_service.handle_context_menu_event(event)
        return super().contextMenuEvent(event)
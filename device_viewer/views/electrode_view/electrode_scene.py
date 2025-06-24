from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QGraphicsScene

from .electrode_view_helpers import find_path_item
from .electrodes_view_base import ElectrodeView, ElectrodeConnectionItem
from microdrop_utils._logger import get_logger

logger = get_logger(__name__, level='DEBUG')


class ElectrodeScene(QGraphicsScene):
    """
    Class to handle electrode view scene using elements contained in the electrode layer.
    Handles identifying mouse action across the scene.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.left_mouse_pressed = False
        self.right_mouse_pressed = False
        self.is_drag = False
        self.last_electrode_id_visited = None
        self._interaction_service = None

    @property
    def interaction_service(self):
        #: The service handling electrode interactions
        return self._interaction_service

    @interaction_service.setter
    def interaction_service(self, interaction_service):
        self._interaction_service = interaction_service

    def get_item_under_mouse(self, coordinates: QPointF, object_type):
        '''
        Searches for an object with type object_type in the scene at coordinates. This will be able to find items at lower z indexes. 
        '''
        # Because QGraphicsScene is so primitive, we need to manually get item under the mouse click via coordinates since we can't use signals (QGraphicsItem is not a QObject)
        # Event bubbling (using the mousePressEvent from the ElectrodeView) has some strange behaviour, so this approach is used instead
        items = self.items(coordinates)
        for item in items:
            if isinstance(item, object_type):
                return item
        return None

    def mousePressEvent(self, event):
        """Handle the start of a mouse click event."""

        button = event.button()
        mode = self.interaction_service.get_mode()

        if button == Qt.LeftButton:
            self.left_mouse_pressed = True
            electrode_view = self.get_item_under_mouse(event.scenePos(), ElectrodeView)
            if mode in ("edit", "draw"):
                if electrode_view:
                    self.last_electrode_id_visited = electrode_view.id
            elif mode == "auto":
                if electrode_view:
                    self.interaction_service.handle_autoroute_start(electrode_view.id)
                else: # No electrode clicked, exit autoroute mode
                    self.interaction_service.set_mode("edit")

        elif button == Qt.RightButton:
            self.right_mouse_pressed = True

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle the dragging motion."""

        if self.left_mouse_pressed:
            # Only proceed if we have a valid electrode view.
            electrode_view = self.get_item_under_mouse(event.scenePos(), ElectrodeView)
            mode = self.interaction_service.get_mode()
            if mode in ("edit", "draw"):
                if electrode_view:
                    if self.last_electrode_id_visited == None: # No electrode clicked yet (for example, first click was not on electrode)
                        self.last_electrode_id_visited = electrode_view.id
                    else:
                        found_connection_item = find_path_item(self, (self.last_electrode_id_visited, electrode_view.id))
                        if found_connection_item is not None: # Are the electrodes neigbors? (This excludes self)
                            self.interaction_service.handle_route_draw(self.last_electrode_id_visited, electrode_view.id)
                            self.last_electrode_id_visited = electrode_view.id
                            self.is_drag = True # Since more than one electrode is left clicked, its a drag, not a single electrode click
            elif mode == "auto":
                if electrode_view:
                    self.interaction_service.handle_autoroute(electrode_view.id) # We store last_electrode_id_visited as the source node
                        
        if self.right_mouse_pressed:
            connection_item = self.get_item_under_mouse(event.scenePos(), ElectrodeConnectionItem)
            if connection_item:
                (from_id, to_id) = connection_item.key
                self.interaction_service.handle_route_erase(from_id, to_id)
                
                    

        # Call the base class mouseMoveEvent to ensure normal processing continues.
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finalize the drag operation."""
        button = event.button()

        if button == Qt.LeftButton:
            self.left_mouse_pressed = False
            mode = self.interaction_service.get_mode()
            if mode in ["edit", "draw"]:
                # If it's a click (not a drag) since only one electrode selected:
                if not self.is_drag:
                    if self.interaction_service:
                        self.interaction_service.handle_electrode_click(self.last_electrode_id_visited)
                
                # Reset left-click related vars
                self.is_drag = False
            elif mode == "auto":
                self.interaction_service.handle_autoroute_end()
        elif button == Qt.RightButton:
            self.right_mouse_pressed = False
        
        super().mouseReleaseEvent(event)

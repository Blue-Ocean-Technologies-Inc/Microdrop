from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QGraphicsScene

from .electrode_view_helpers import find_path_item
from .electrodes_view_base import ElectrodeView
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
        self.electrode_channels_visited = []
        self.electrode_ids_visited = []
        self._interaction_service = None

    @property
    def interaction_service(self):
        #: The service handling electrode interactions
        return self._interaction_service

    @interaction_service.setter
    def interaction_service(self, interaction_service):
        self._interaction_service = interaction_service

    def get_item_under_mouse(self, coordinates: QPointF):
        # Because QGraphicsScene is so primitive, we need to manually get item under the mouse click via coordinates since we can't use signals (QGraphicsItem is not a QObject)
        # Event bubbling (using the mousePressEvent from the ElectrodeView) has some strange behaviour, so this approach is used instead
        items = self.items(coordinates)
        for item in items:
            if isinstance(item, ElectrodeView):
                return item
        return None

    def add_electrode_to_path(self, electrode_view):
        # Append new channel and electrode ID to their respective lists.
        self.electrode_channels_visited.append(electrode_view.electrode.channel)
        self.electrode_ids_visited.append(electrode_view.id)

        logger.debug(f"path will be {'->'.join(str(i) for i in self.electrode_channels_visited)}")

    def mousePressEvent(self, event):
        """Handle the start of a mouse click event."""

        if event.button() == Qt.LeftButton:
            self.mouseLeftClickEvent(event)

            super().mousePressEvent(event)

    def mouseLeftClickEvent(self, event):
        # Get the item under the mouse click using the scene's coordinates.
        self.left_mouse_pressed = True

        electrode_view = self.get_item_under_mouse(event.scenePos())

        if electrode_view:
            # Track the visited electrode IDs and channels.
            self.electrode_channels_visited = [electrode_view.electrode.channel]
            self.electrode_ids_visited = [electrode_view.id]


    def mouseMoveEvent(self, event):
        """Handle the dragging motion."""
        if self.left_mouse_pressed:
            # Identify the new item under the mouse cursor using the scene's transform.
            electrode_view = self.get_item_under_mouse(event.scenePos())

            # Only proceed if we have a valid electrode view.
            if electrode_view:
                if len(self.electrode_ids_visited) == 0: # Electrode list is empty (for example, first click was not on electrode)
                    self.add_electrode_to_path(electrode_view)
                else:
                    found_connection_item = find_path_item(self, (self.electrode_ids_visited[-1], electrode_view.id))
                    if found_connection_item is not None: # Are the electrodes neigbors? (This excludes self)
                        self.add_electrode_to_path(electrode_view)
                        found_connection_item.update_color()
                    

        # Call the base class mouseMoveEvent to ensure normal processing continues.
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finalize the drag operation."""

        # If it's a click (not a drag) since only one electrode selected:
        if len(self.electrode_channels_visited) == 1:
            if self.interaction_service:
                self.interaction_service.handle_electrode_click(self.electrode_ids_visited[0])

        else:
            logger.info(self.electrode_channels_visited)
            # TODO: Implement the logic to handle the mouse release event. Add header to the path and indicate CW & CCW rotation for closed loops
            

        self.left_mouse_pressed = False
        self.electrode_channels_visited = []
        self.electrode_ids_visited = []
        super().mouseReleaseEvent(event)

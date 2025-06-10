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
        self.electrode_pressed = None
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

    def mousePressEvent(self, event):
        """Handle the start of a mouse click event."""

        if event.button() == Qt.LeftButton:
            self.mouseLeftClickEvent(event)

            super().mousePressEvent(event)

    def mouseLeftClickEvent(self, event):
        # Get the item under the mouse click using the scene's coordinates.
        electrode_view = self.get_item_under_mouse(event.scenePos())

        if electrode_view is None:
            return

        # Record the clicked electrode view and initialize route tracking.
        self.electrode_pressed = electrode_view

        # Track the visited electrode IDs and channels.
        self.electrode_channels_visited = [electrode_view.electrode.channel]
        self.electrode_ids_visited = [electrode_view.id]

    def mouseMoveEvent(self, event):
        """Handle the dragging motion."""
        if self.electrode_pressed:
            # Identify the new item under the mouse cursor using the scene's transform.
            electrode_view = self.get_item_under_mouse(event.scenePos())

            # Only proceed if we have a valid electrode view.
            if electrode_view:
                channel_ = electrode_view.electrode.channel

                # Check if this channel differs from the last visited channel.
                if self.electrode_channels_visited[-1] != channel_:
                    # Append new channel and electrode ID to their respective lists.
                    self.electrode_channels_visited.append(channel_)
                    self.electrode_ids_visited.append(electrode_view.id)

                    # Determine the key for path lookup based on the last two visited electrodes.
                    src_key = self.electrode_ids_visited[-2]
                    dst_key = self.electrode_ids_visited[-1]
                    key = (src_key, dst_key)
                    
                    # Find the corresponding path item and update its visual representation.
                    found_item = find_path_item(self, key)
                    if found_item is not None:
                        found_item.update_color()
                        logger.debug(f"path will be {'->'.join(str(i) for i in self.electrode_channels_visited)}")

                # Update the electrode pressed to the current electrode view.
                self.electrode_pressed = electrode_view

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
            

        self.electrode_pressed = None
        self.electrode_channels_visited = []
        super().mouseReleaseEvent(event)

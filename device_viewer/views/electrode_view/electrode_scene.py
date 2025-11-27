from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QKeyEvent, QAction
from PySide6.QtWidgets import QGraphicsScene, QMenu, QGraphicsSceneContextMenuEvent

from .electrode_view_helpers import find_path_item
from .electrodes_view_base import ElectrodeView, ElectrodeConnectionItem, ElectrodeEndpointItem
from logger.logger_service import get_logger
from .scale_edit_view import ScaleEditViewController
from ...services.electrode_interaction_service import ElectrodeInteractionControllerService

logger = get_logger(__name__, level='DEBUG')

class ElectrodeScene(QGraphicsScene):
    """
    Class to handle electrode view scene using elements contained in the electrode layer.
    Handles identifying mouse action across the scene.
    """

    def __init__(self, dockpane, parent=None):
        super().__init__(parent)
        self.electrode_tooltip_visible = True
        self.dockpane = dockpane
        self.left_mouse_pressed = False
        self.right_mouse_pressed = False
        self.electrode_view_right_clicked = None
        self.is_drag = False
        self.last_electrode_id_visited = None
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
        char = event.text()
        key = event.key()

        if char.isprintable(): # If an actual char was inputted
            if char.isdigit(): # It's a digit
                self.interaction_service.handle_digit_input(char)
        else:
            if key == Qt.Key_Backspace:
                self.interaction_service.handle_backspace()

        if (event.modifiers() & Qt.ControlModifier):
            if event.key() == Qt.Key_Right:
                self.interaction_service.handle_ctrl_key_right()

            elif event.key() == Qt.Key_Left:
                self.interaction_service.handle_ctrl_key_left()

        if (event.modifiers() & Qt.AltModifier):
            if event.key() == Qt.Key_Right:
                self.interaction_service.handle_alt_key_right()

            elif event.key() == Qt.Key_Left:
                self.interaction_service.handle_alt_key_left()

        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Handle the start of a mouse click event."""

        button = event.button()
        mode = self.interaction_service.get_mode()

        if button == Qt.LeftButton:
            self.left_mouse_pressed = True
            electrode_view = self.get_item_under_mouse(event.scenePos(), ElectrodeView)

            if mode in ("edit", "draw", "edit-draw"):
                if electrode_view:
                    self.last_electrode_id_visited = electrode_view.id

            elif mode == "auto":
                if electrode_view:
                    self.interaction_service.handle_autoroute_start(electrode_view.id)
                else: # No electrode clicked, exit autoroute mode
                    self.interaction_service.set_mode("edit")

            elif mode == "channel-edit":
                if electrode_view:
                    self.interaction_service.handle_electrode_channel_editing(electrode_view.electrode)

            elif mode == "camera-place":
                self.interaction_service.handle_reference_point_placement(event.scenePos())

            elif mode == "camera-edit":
                self.interaction_service.handle_perspective_edit_start(event.scenePos())

        elif button == Qt.RightButton:
            self.right_mouse_pressed = True
            self.electrode_view_right_clicked = self.get_item_under_mouse(event.scenePos(), ElectrodeView)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle the dragging motion."""

        mode = self.interaction_service.get_mode()
        electrode_view = self.get_item_under_mouse(event.scenePos(), ElectrodeView)
        self.interaction_service.handle_electrode_hover(electrode_view)

        if self.left_mouse_pressed:
            # Only proceed if we have a valid electrode view.
            if mode in ("edit", "draw", "edit-draw"):
                if electrode_view:
                    if self.last_electrode_id_visited == None: # No electrode clicked yet (for example, first click was not on electrode)
                        self.last_electrode_id_visited = electrode_view.id
                    else:
                        found_connection_item = find_path_item(self, (self.last_electrode_id_visited, electrode_view.id))
                        if found_connection_item is not None: # Are the electrodes neigbors? (This excludes self)
                            self.interaction_service.handle_route_draw(self.last_electrode_id_visited, electrode_view.id)
                            self.last_electrode_id_visited = electrode_view.id # TODO: Move this outside of if clause, last_electrode_id_visited should always be the last hovered
                            self.is_drag = True # Since more than one electrode is left clicked, its a drag, not a single electrode click
                        
            elif mode == "auto":
                if electrode_view:
                    self.interaction_service.handle_autoroute(electrode_view.id) # We store last_electrode_id_visited as the source node
            
            elif mode == "camera-edit":
                self.interaction_service.handle_perspective_edit(event.scenePos())

        if self.right_mouse_pressed:
            if mode in ("edit", "draw", "edit-draw") and event.modifiers() & Qt.ControlModifier:
                connection_item = self.get_item_under_mouse(event.scenePos(), ElectrodeConnectionItem)
                endpoint_item = self.get_item_under_mouse(event.scenePos(), ElectrodeEndpointItem)
                if connection_item:
                    (from_id, to_id) = connection_item.key
                    self.interaction_service.handle_route_erase(from_id, to_id)
                elif endpoint_item:
                    self.interaction_service.handle_endpoint_erase(endpoint_item.electrode_id)

        # Call the base class mouseMoveEvent to ensure normal processing continues.
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finalize the drag operation."""
        button = event.button()

        if button == Qt.LeftButton:
            self.left_mouse_pressed = False
            mode = self.interaction_service.get_mode()  
            if mode == "auto":
                self.interaction_service.handle_autoroute_end()
            elif mode in ("edit", "draw", "edit-draw"):
                electrode_view = self.get_item_under_mouse(event.scenePos(), ElectrodeView)
                # If it's a click (not a drag) since only one electrode selected:
                if not self.is_drag and electrode_view:
                    self.interaction_service.handle_electrode_click(electrode_view.id)
                
                # Reset left-click related vars
                self.is_drag = False

                if mode == "edit-draw": # Go back to draw
                    self.interaction_service.set_mode("draw")
            elif mode == "camera-edit":
                self.interaction_service.handle_perspective_edit_end()
        elif button == Qt.RightButton:
            self.right_mouse_pressed = False
        
        super().mouseReleaseEvent(event)

    def detect_droplet(self):
        """Placeholder for a context menu action."""
        self.dockpane.publish_detect_droplet()

    def measure_filler_capacitance(self):
        """Placeholder for measuring filler capacitance."""
        if not self.interaction_service.model.electrodes.any_electrode_on():
            logger.warning("No electrodes are on, cannot measure filler capacitance.")
            return
        
        if self.dockpane.last_capacitance is None:
            logger.warning("No capacitance value available to set for filler capacitance.")
            return
        
        self.interaction_service.model.filler_capacitance_over_area = self.dockpane.last_capacitance / self.interaction_service.model.electrodes.get_activated_electrode_area_mm2()

    def measure_liquid_capacitance(self):
        """Placeholder for measuring liquid capacitance."""
        if not self.interaction_service.model.electrodes.any_electrode_on():
            logger.warning("No electrodes are on, cannot measure liquid capacitance.")
            return
        
        if self.dockpane.last_capacitance is None:
            logger.warning("No capacitance value available to set for liquid capacitance.")
            return

        self.interaction_service.model.liquid_capacitance_over_area = self.dockpane.last_capacitance / self.interaction_service.model.electrodes.get_activated_electrode_area_mm2()

    def adjust_electrode_area_scale(self):
        """Placeholder for adjusting electrode area."""
        
        scale_edit_view_controller = ScaleEditViewController(model=self.electrode_view_right_clicked.electrode,
                                                             electrode_interaction_service=self.interaction_service)
        scale_edit_view_controller.configure_traits()

    def handle_toggle_electrode_tooltips(self, checked):
        """Handle toggle electrode tooltip."""
        self.electrode_tooltip_visible = checked
        self.interaction_service.handle_toggle_electrode_tooltip(checked)

    def contextMenuEvent(self, event : QGraphicsSceneContextMenuEvent):
        if event.modifiers() & Qt.ControlModifier:
            # If control is pressed, we do not show the context menu
            return super().contextMenuEvent(event)

        context_menu = QMenu()
        context_menu.addAction("Measure Liquid Capacitance", self.measure_liquid_capacitance)
        context_menu.addAction("Measure Filler Capacitance", self.measure_filler_capacitance)
        context_menu.addSeparator()
        context_menu.addAction("Reset Electrodes", self.interaction_service.model.electrodes.reset_electrode_states)
        context_menu.addAction("Find Liquid", self.detect_droplet)

        if self.electrode_view_right_clicked is not None:
            context_menu.addAction("Adjust Electrode Area Scale", self.adjust_electrode_area_scale)
        context_menu.addSeparator()

        # tooltip enabled by default
        tooltip_toggle_action = QAction("Enable Electrode Tooltip", checkable=True,
                                        checked=self.electrode_tooltip_visible)

        tooltip_toggle_action.triggered.connect(self.handle_toggle_electrode_tooltips)

        context_menu.addAction(tooltip_toggle_action)

        context_menu.exec(event.screenPos())
        return super().contextMenuEvent(event)

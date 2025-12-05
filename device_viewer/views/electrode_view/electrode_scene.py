from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QKeyEvent, QAction
from PySide6.QtWidgets import QGraphicsScene, QMenu, QGraphicsSceneContextMenuEvent

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
        self.electrode_view_right_clicked = None
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
        # Call the base class mouseMoveEvent to ensure normal processing continues.
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finalize the drag operation."""

        self.interaction_service.handle_mouse_release_event(event)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if not self.interaction_service.handle_wheel_event(event):
            super().wheelEvent(event)

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

# enthought imports
import dramatiq
from traits.api import Instance, observe, Any, Str, provides
from pyface.api import FileDialog, OK
from pyface.tasks.dock_pane import DockPane
from pyface.qt.QtGui import QGraphicsScene
from pyface.qt.QtOpenGLWidgets import QOpenGLWidget
from pyface.qt.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from pyface.qt.QtCore import Qt, QTimer
from pyface.tasks.api import TraitsDockPane
from pyface.undo.api import UndoManager, CommandStack

# local imports
# TODO: maybe get these from an extension point for very granular control
from device_viewer.views.electrode_view.electrode_scene import ElectrodeScene
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from microdrop_utils.dramatiq_controller_base import basic_listener_actor_routine, generate_class_method_dramatiq_listener_actor
from ..utils.auto_fit_graphics_view import AutoFitGraphicsView
from ..utils.message_utils import gui_models_to_message_model
from ..models.messages import DeviceViewerMessageModel
from microdrop_utils._logger import get_logger
from device_viewer.models.electrodes import Electrodes
from device_viewer.models.route import RouteLayerManager, Route
from device_viewer.consts import DEFAULT_SVG_FILE, PKG, PKG_name
from device_viewer.services.electrode_interaction_service import ElectrodeInteractionControllerService
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import ELECTRODES_STATE_CHANGE
from ..consts import listener_name
from device_viewer.views.route_selection_view.route_selection_view import RouteLayerView
from device_viewer.views.mode_picker.widget import ModePicker
from device_viewer.utils.device_viewer_state_command import DeviceViewerStateCommand
import json

logger = get_logger(__name__)

class DeviceViewerDockPane(TraitsDockPane):
    """
    A widget for viewing the device. This puts the electrode layer into a graphics view.
    """

    # ----------- Device View Pane traits ---------------------

    undo_manager = Instance(UndoManager)

    electrodes_model = Instance(Electrodes)
    route_layer_manager = Instance(RouteLayerManager)

    id = PKG + ".pane"
    name = PKG_name + " Dock Pane"

    scene = Instance(QGraphicsScene)
    device_view = Instance(AutoFitGraphicsView)
    current_electrode_layer = Instance(ElectrodeLayer, allow_none=True)
    layer_ui = None
    mode_picker_view = None
    _undoing = False

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    # --------- Dramatiq Init ------------------------------
    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    # --------- Device View trait initializers -------------
    def traits_init(self):
        logger.info("Starting DeviceViewer listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine)
        self.publish_model_message() # First message when all models are initialised

    def _electrodes_model_default(self):
        electrodes = Electrodes()
        electrodes.set_electrodes_from_svg_file(DEFAULT_SVG_FILE)
        return electrodes
    
    def _route_layer_manager_default(self):
        return RouteLayerManager()

    def _scene_default(self):
        return ElectrodeScene()

    def _device_view_default(self):
        view = AutoFitGraphicsView(self.scene)
        view.setObjectName('device_view')
        view.setViewport(QOpenGLWidget())

        return view

    def _undo_manager_default(self):
        undo_manager = UndoManager(active_stack=CommandStack())
        undo_manager.active_stack.undo_manager = undo_manager
        return undo_manager

    # ------- Dramatiq handlers ---------------------------
    def _on_chip_inserted(self, message):
        if message == "True" and self.electrodes_model and self.route_layer_manager:
            self.publish_model_message()

    # ------- Device View class methods -------------------------
    def set_electrodes_model(self, new_electrodes_model):
        """Handle when the electrodes model changes."""

        # Trigger an update to redraw and re-initialize the svg widget once a new svg file is selected.
        self.set_view_from_model(new_electrodes_model)
        logger.debug(f"New Electrode Layer added --> {new_electrodes_model.svg_model.filename}")

        # Since were using traitsui for the layer viewer, its really difficult to simply reassign the model
        self.route_layer_manager.reset() # So we just reset internal state

        # Initialize the electrode mouse interaction service with the new model and layer
        interaction_service = ElectrodeInteractionControllerService(
            electrodes_model=new_electrodes_model,
            route_layer_manager=self.route_layer_manager,
            electrode_view_layer=self.current_electrode_layer
        )

        # Update the scene with the interaction service
        self.scene.interaction_service = interaction_service

        logger.debug(f"Setting up handlers for new layer for new electrodes model {new_electrodes_model}")


    def remove_current_layer(self):
        """
        Utility methods to remove current scene's electrode layer.
        """
        if self.current_electrode_layer:
            self.current_electrode_layer.remove_all_items_to_scene(self.scene)
            self.scene.clear()
            self.scene.update()

    @observe("electrodes_model._electrodes.items.state") # When an electrode changes state
    @observe("route_layer_manager.layers.items.route.route.items") # When a route is modified
    @observe("electrodes_model") # When the entire electrodes model is reassigned. Note that the route_manager model should never be reassigned (because of TraitsUI)
    def model_change_handler(self, event=None):
        self.debounce_timer.start(1000) # Start timeout for sending message

        if not self._undoing:
            self.undo_manager.active_stack.push(DeviceViewerStateCommand(data=self))

    def undo(self):
        self._undoing = True # We need to prevent the changes made in undo() from being added to the undo stack
        self.undo_manager.undo()
        self._undoing = False

    def apply_message_model(self, message_model: DeviceViewerMessageModel, fullreset=False):
        # Apply electrode on/off states
        for electrode_id, electrode in self.electrodes_model.electrodes.items():
            electrode.state = message_model.channels_activated[electrode.channel]
        
        # Apply routes
        if fullreset:
            self.route_layer_manager.reset()
        else:
            self.route_layer_manager.layers.clear() # Clear all layers
            self.route_layer_manager.selected_layer = None # Deselect all layers
            self.route_layer_manager.layer_to_merge = None # Reset merge layer
            if self.route_layer_manager.mode == "merge":
                self.route_layer_manager.mode = "edit" # Reset mode to edit if we were in merge mode
        
        for route, color in message_model.routes:
            self.route_layer_manager.add_layer(Route(route), None, color)


    def publish_model_message(self):
        message_model = gui_models_to_message_model(self.electrodes_model, self.route_layer_manager)
        message = message_model.serialize()
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=message) # TODO: Change topic to UI topic protocol_grid expects

    def create_contents(self, parent):
        """Called when the task is activated."""
        logger.debug(f"Device Viewer Task activated. Setting default view with {DEFAULT_SVG_FILE}...")
        self.set_electrodes_model(self.electrodes_model)

        # Create debouce timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.publish_model_message)

        # Layout init
        container = QWidget(parent)
        layout = QHBoxLayout(container)
        left_stack = QVBoxLayout()

        # device_view code
        self.device_view.setParent(container)

        # layer_view code
        layer_model = self.route_layer_manager
        layer_view = RouteLayerView
        self.layer_ui = layer_model.edit_traits(view=layer_view)
        # self.layer_ui.control is the underlying Qt widget which we have to access to attach to layout
        self.layer_ui.control.setFixedWidth(250) # Set widget to fixed width
        self.layer_ui.control.setParent(container)

        # mode_picker_view code
        self.mode_picker_view = ModePicker(layer_model, self.electrodes_model, self)
        self.mode_picker_view.setParent(container)

        # Add widgets to layouts
        left_stack.addWidget(self.layer_ui.control)
        left_stack.addWidget(self.mode_picker_view)
        
        layout.addWidget(self.device_view)
        layout.addLayout(left_stack)

        return container

    def set_view_from_model(self, new_model):
        self.remove_current_layer()
        self.current_electrode_layer = ElectrodeLayer(new_model)
        self.current_electrode_layer.add_all_items_to_scene(self.scene)
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self.device_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def open_file_dialog(self):
        """Open a file dialog to select an SVG file and set it in the central pane."""
        dialog = FileDialog(action='open', wildcard='SVG Files (*.svg)|*.svg|All Files (*.*)|*.*')
        if dialog.open() == OK:
            svg_file = dialog.path
            logger.info(f"Selected SVG file: {svg_file}")

            new_model = Electrodes()
            new_model.set_electrodes_from_svg_file(svg_file)
            logger.debug(f"Created electrodes from SVG file: {new_model.svg_model.filename}")

            self.set_electrodes_model(new_model)
            logger.info(f"Electrodes model set to {new_model}")
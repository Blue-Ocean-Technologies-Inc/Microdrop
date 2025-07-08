# enthought imports
import dramatiq
from traits.api import Instance, observe, Any, Str, provides
from traits.observation.events import ListChangeEvent, TraitChangeEvent, DictChangeEvent
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
from device_viewer.models.main_model import MainModel
from device_viewer.models.route import RouteLayerManager, Route
from device_viewer.consts import DEFAULT_SVG_FILE, PKG, PKG_name
from device_viewer.services.electrode_interaction_service import ElectrodeInteractionControllerService
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import ELECTRODES_STATE_CHANGE
from ..consts import listener_name
from device_viewer.views.route_selection_view.route_selection_view import RouteLayerView
from device_viewer.views.mode_picker.widget import ModePicker
from device_viewer.utils.commands import TraitChangeCommand, ListChangeCommand, DictChangeCommand
from protocol_grid.consts import DEVICE_VIEWER_STATE_CHANGED
import json

logger = get_logger(__name__)

class DeviceViewerDockPane(TraitsDockPane):
    """
    A widget for viewing the device. This puts the electrode layer into a graphics view.
    """

    # ----------- Device View Pane traits ---------------------

    undo_manager = Instance(UndoManager)

    model = Instance(MainModel)

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

    def _model_default(self):
        model = MainModel()
        model.set_electrodes_from_svg_file(DEFAULT_SVG_FILE)
        return model

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
        if message == "True" and self.model:
            self.publish_model_message()

    # ------- Device View class methods -------------------------
    def set_model(self, new_model):
        """Handle when the electrodes model changes."""

        # Trigger an update to redraw and re-initialize the svg widget once a new svg file is selected.
        self.set_view_from_model(new_model)
        logger.debug(f"New Electrode Layer added --> {new_model.svg_model.filename}")

        # Since were using traitsui for the layer viewer, its really difficult to simply reassign the model
        self.model.reset() # So we just reset internal state

        # Initialize the electrode mouse interaction service with the new model and layer
        interaction_service = ElectrodeInteractionControllerService(
            model=new_model,
            electrode_view_layer=self.current_electrode_layer
        )

        # Update the scene with the interaction service
        self.scene.interaction_service = interaction_service
        self.scene.interaction_service.electrode_state_recolor(None)

        logger.debug(f"Setting up handlers for new layer for new electrodes model {new_model}")


    def remove_current_layer(self):
        """
        Utility methods to remove current scene's electrode layer.
        """
        if self.current_electrode_layer:
            self.current_electrode_layer.remove_all_items_to_scene(self.scene)
            self.scene.clear()
            self.scene.update()

    def add_traits_event_to_undo_stack(self, event):
        command = None
        if isinstance(event, TraitChangeEvent):
            command = TraitChangeCommand(event=event)
        elif isinstance(event, ListChangeEvent):
            command = ListChangeCommand(event=event)
        elif isinstance(event, DictChangeEvent):
            command = DictChangeCommand(event=event)
        self.undo_manager.active_stack.push(command)

    @observe("model") # When the entire electrodes model is reassigned. Note that the route_manager model should never be reassigned (because of TraitsUI)
    @observe("model.layers.items.route.route.items") # When a route is modified
    @observe("model.layers.items") # When an electrode changes state
    @observe("model.electrodes.items.channel") # When a electrode's channel is modified (i.e. using channel-edit mode)
    @observe("model.channels_states_map.items") # When an electrode changes state
    def model_change_handler_with_timeout(self, event=None):
        if not self._undoing:
            self.add_traits_event_to_undo_stack(event)
        self.debounce_timer.start(700) # Start timeout for sending message
    
    @observe("model.channels_states_map.items") # When an electrode changes state
    def electrode_click_handler(self, event=None):
        logger.info("Sending electrode update")
        self.publish_electrode_update()
        logger.info("Electrode update sent")

    def undo(self):
        self._undoing = True # We need to prevent the changes made in undo() from being added to the undo stack
        self.undo_manager.undo()
        self._undoing = False

    def redo(self):
        self._undoing = True # We need to prevent the changes made in redo() from being added to the undo stack
        self.undo_manager.redo()
        self._undoing = False

    def apply_message_model(self, message_model: DeviceViewerMessageModel, fullreset=False):
        # Apply electrode on/off states
        for electrode_id, electrode in self.model.electrodes.items():
            electrode.state = message_model.channels_activated[electrode.channel]
        
        # Apply routes
        if fullreset:
            self.model.reset()
        else:
            self.model.layers.clear() # Clear all layers
            self.model.selected_layer = None # Deselect all layers
            self.model.layer_to_merge = None # Reset merge layer
            if self.model.mode == "merge":
                self.model.mode = "edit" # Reset mode to edit if we were in merge mode
        
        for route, color in message_model.routes:
            self.model.add_layer(Route(route), None, color)


    def publish_model_message(self):
        message_model = gui_models_to_message_model(self.model)
        message = message_model.serialize()
        publish_message(topic=DEVICE_VIEWER_STATE_CHANGED, message=message) # TODO: Change topic to UI topic protocol_grid expects

    def publish_electrode_update(self):
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(self.model.channels_states_map))

    def create_contents(self, parent):
        """Called when the task is activated."""
        logger.debug(f"Device Viewer Task activated. Setting default view with {DEFAULT_SVG_FILE}...")
        self.set_model(self.model)

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
        layer_view = RouteLayerView
        self.layer_ui = self.model.edit_traits(view=layer_view)
        # self.layer_ui.control is the underlying Qt widget which we have to access to attach to layout
        self.layer_ui.control.setFixedWidth(250) # Set widget to fixed width
        self.layer_ui.control.setParent(container)

        # mode_picker_view code
        self.mode_picker_view = ModePicker(self.model, self)
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

            new_model = MainModel()
            new_model.set_electrodes_from_svg_file(svg_file)
            logger.debug(f"Created electrodes from SVG file: {new_model.svg_model.filename}")

            self.set_model(new_model)
            logger.info(f"Electrodes model set to {new_model}")
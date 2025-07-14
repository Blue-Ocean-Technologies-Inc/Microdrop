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
from device_viewer.utils.dmf_utils import channels_to_svg
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

    def _on_display_state_triggered(self, message_model_serial: str):
        # We send the message through a signal since Dramatiq runs the callbacks in a separate thread
        # Which has weird side effects on QtGraphicsObject calls
        self.device_view.display_state_signal.emit(message_model_serial)


    # ------- Device View class methods -------------------------
    def set_interaction_service(self, new_model):
        """Handle when the electrodes model changes."""

        # Trigger an update to redraw and re-initialize the svg widget once a new svg file is selected.
        self.set_view_from_model(new_model)
        logger.debug(f"New Electrode Layer added --> {new_model.svg_model.filename}")

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
        if self.model.step_id is None: # Only send electrode updates if we are in free mode (no step_id)
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

    def apply_message_model(self, message_model_serial: str):
        logger.debug(f"Display state triggered with model: {message_model_serial}")
        # Reset the model to clear any existing routes and channels
        self.undo_manager.active_stack.clear()  # Clear the undo stack
        self._undoing = True  # Prevent changes from being added to the undo stack
        self.model.reset()

        message_model = DeviceViewerMessageModel.deserialize(message_model_serial)

        # Apply step ID
        self.model.step_id = message_model.step_id

        # Apply electrode channel mapping
        for electrode_id, electrode in self.model.electrodes.items():
            electrode.channel = message_model.id_to_channel.get(electrode_id, electrode.channel)

        # Apply electrode on/off states
        self.model.channels_states_map.update(message_model.channels_activated)

        # Apply routes
        for route, color in message_model.routes:
            self.model.add_layer(Route(route=route.copy()), None, color)
        self.model.selected_layer = None

        self._undoing = False  # Re-enable undo/redo after reset
        


    def publish_model_message(self):
        message_model = gui_models_to_message_model(self.model)
        message = message_model.serialize()
        logger.debug(f"Publishing message for updated viewer state {message}")
        publish_message(topic=DEVICE_VIEWER_STATE_CHANGED, message=message)

    def publish_electrode_update(self):
        message_obj = {}
        for channel in self.model.channels_electrode_ids_map: # Make sure all channels are explicitly included
            message_obj[channel] = self.model.channels_states_map.get(channel, False)
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(message_obj))

    def create_contents(self, parent):
        """Called when the task is activated."""
        logger.debug(f"Device Viewer Task activated. Setting default view with {DEFAULT_SVG_FILE}...")
        self.set_interaction_service(self.model)

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
        self.device_view.display_state_signal.connect(self.apply_message_model)

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
        self.undo_manager.active_stack.clear()

    def open_file_dialog(self):
        """Open a file dialog to select an SVG file and set it in the central pane."""
        dialog = FileDialog(action='open', wildcard='SVG Files (*.svg)|*.svg|All Files (*.*)|*.*')
        if dialog.open() == OK:
            svg_file = dialog.path
            logger.info(f"Selected SVG file: {svg_file}")

            self.model.reset()
            self.model.set_electrodes_from_svg_file(svg_file)
            logger.debug(f"Created electrodes from SVG file: {self.model.svg_model.filename}")

            self.set_view_from_model(self.model)
            self.set_interaction_service(self.model)
            logger.info(f"Electrodes model set to {self.model}")

    def open_svg_dialog(self):
        dialog = FileDialog(action='save as', wildcard='SVG Files (*.svg)|*.svg')
        if dialog.open() == OK:
            new_filename = dialog.path if dialog.path.endswith(".svg") else str(dialog.path) + ".svg"
            channels_to_svg(self.model.svg_model.filename, new_filename, self.model.electrode_ids_channels_map)
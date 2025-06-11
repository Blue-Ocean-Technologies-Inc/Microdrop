# enthought imports
import dramatiq
from traits.api import Instance
from pyface.api import FileDialog, OK
from pyface.tasks.dock_pane import DockPane
from pyface.qt.QtGui import QGraphicsScene
from pyface.qt.QtOpenGLWidgets import QOpenGLWidget
from pyface.qt.QtCore import Qt

# local imports
# TODO: maybe get these from an extension point for very granular control
from device_viewer.views.electrode_view.electrode_scene import ElectrodeScene
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from microdrop_utils.dramatiq_controller_base import basic_listener_actor_routine, generate_class_method_dramatiq_listener_actor
from ..utils.auto_fit_graphics_view import AutoFitGraphicsView
from microdrop_utils._logger import get_logger
from device_viewer.models.electrodes import Electrodes
from device_viewer.consts import DEFAULT_SVG_FILE, PKG, PKG_name
from device_viewer.services.electrode_interaction_service import ElectrodeInteractionControllerService
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import ELECTRODES_STATE_CHANGE
from ..consts import listener_name
import json

logger = get_logger(__name__)


class DeviceViewerDockPane(DockPane):
    """
    A widget for viewing the device. This puts the electrode layer into a graphics view.
    """

    # ----------- Device View Pane traits ---------------------

    electrodes_model = Instance(Electrodes)

    id = PKG + ".pane"
    name = PKG_name + " Dock Pane"

    scene = Instance(QGraphicsScene)
    view = Instance(AutoFitGraphicsView)
    current_electrode_layer = Instance(ElectrodeLayer, allow_none=True)

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    # --------- Dramatiq Init ------------------------------
    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    # --------- Device View trait initializers -------------
    def traits_init(self):
        logger.info("Starting ManualControls listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine)

    def _electrodes_model_default(self):
        electrodes = Electrodes()
        electrodes.set_electrodes_from_svg_file(DEFAULT_SVG_FILE)
        return electrodes

    def _scene_default(self):
        return ElectrodeScene()

    def _view_default(self):
        view = AutoFitGraphicsView(self.scene)
        view.setObjectName('device_view')
        view.setViewport(QOpenGLWidget())

        return view
    
    # --------- Trait change handlers ----------------------------
    def _electrodes_model_changed(self, new_model):
        """Handle when the electrodes model changes."""

        # Trigger an update to redraw and re-initialize the svg widget once a new svg file is selected.
        self.set_view_from_model(new_model)
        logger.debug(f"New Electrode Layer added --> {new_model.svg_model.filename}")

        # Initialize the electrode mouse interaction service with the new model and layer
        interaction_service = ElectrodeInteractionControllerService(
            electrodes_model=new_model,
            electrode_view_layer=self.current_electrode_layer
        )

        # Update the scene with the interaction service
        self.scene.interaction_service = interaction_service

        logger.debug(f"Setting up handlers for new layer for new electrodes model {new_model}")
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(self.electrodes_model.channels_states_map))

    # ------- Dramatiq handlers ---------------------------
    def _on_chip_inserted(self, message):
        if message == "True" and self.electrodes_model:
            publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(self.electrodes_model.channels_states_map))

    # ------- Device View class methods -------------------------
    def remove_current_layer(self):
        """
        Utility methods to remove current scene's electrode layer.
        """
        if self.current_electrode_layer:
            self.current_electrode_layer.remove_all_items_to_scene(self.scene)
            self.scene.clear()
            self.scene.update()

    def create_contents(self, parent):
        """Called when the task is activated."""
        logger.debug(f"Device Viewer Task activated. Setting default view with {DEFAULT_SVG_FILE}...")
        self._electrodes_model_changed(self.electrodes_model)

        self.view.setParent(parent)
        return self.view

    def set_view_from_model(self, new_model):
        self.remove_current_layer()
        self.current_electrode_layer = ElectrodeLayer(new_model)
        self.current_electrode_layer.add_all_items_to_scene(self.scene)
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def open_file_dialog(self):
        """Open a file dialog to select an SVG file and set it in the central pane."""
        dialog = FileDialog(action='open', wildcard='SVG Files (*.svg)|*.svg|All Files (*.*)|*.*')
        if dialog.open() == OK:
            svg_file = dialog.path
            logger.info(f"Selected SVG file: {svg_file}")

            new_model = Electrodes()
            new_model.set_electrodes_from_svg_file(svg_file)
            logger.debug(f"Created electrodes from SVG file: {new_model.svg_model.filename}")

            self.electrodes_model = new_model
            logger.info(f"Electrodes model set to {new_model}")
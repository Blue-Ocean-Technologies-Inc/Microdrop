# system imports.
import json
import os
import dramatiq

# Enthought library imports.
from pyface.tasks.action.api import SMenu, SMenuBar, TaskToggleGroup, TaskAction
from pyface.tasks.api import Task, TaskLayout, Tabbed
from pyface.api import FileDialog, OK, GUI
from traits.api import Instance, Str, provides

from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase
# Local imports.
from .models.electrodes import Electrodes
from .views.device_view_pane import DeviceViewerDockPane
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from dropbot_controller.consts import ELECTRODES_STATE_CHANGE
from .services.electrode_interaction_service import ElectrodeInteractionControllerService
from .consts import PKG

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor, \
    basic_listener_actor_routine

from dropbot_tools_menu.self_test_dialogs import WaitForTestDialogAction, ResultsDialogAction

logger = get_logger(__name__, level="DEBUG")
DEFAULT_SVG_FILE = f"{os.path.dirname(__file__)}{os.sep}2x3device.svg"

listener_name = f"{PKG}_listener"


@provides(IDramatiqControllerBase)
class DeviceViewerTask(Task):
    ##########################################################
    # 'IDramatiqControllerBase' interface.
    ##########################################################

    # Child window should be an instance of Dialog Action
    wait_for_test_dialog = Instance(WaitForTestDialogAction)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    listener_name = f"{PKG}_listener"
    
    #### 'DeviceViewerTask' interface #########################
    electrodes_model = Instance(Electrodes)
    
    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    def traits_init(self):
        """
        This function needs to be here to let the listener be initialized to the default value automatically.
        We just do it manually here to make the code clearer.
        We can also do other initialization routines here if needed.

        This is equivalent to doing:

        def __init__(self, **traits):
            super().__init__(**traits)

        """

        logger.info("Starting DeviceViewer listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine)

    #### 'Task' interface #####################################################

    def create_central_pane(self):
        """Create the central pane with the device viewer widget with a default view.
        """

        return DeviceViewerDockPane(electrodes=self.electrodes_model)
    
    def activated(self):
        """Called when the task is activated."""
        logger.debug(f"Device Viewer Task activated. Setting default view with {DEFAULT_SVG_FILE}...")
        _electrodes = Electrodes()
        _electrodes.set_electrodes_from_svg_file(DEFAULT_SVG_FILE)

        self.electrodes_model = _electrodes


    ###########################################################################
    # Protected interface.
    ###########################################################################

    # ------------------ Trait initializers ---------------------------------

    def _default_layout_default(self):
        return TaskLayout(
            left=Tabbed(
            )

        )
    # --------------- Trait change handlers ----------------------------------------------

    def _electrodes_model_changed(self, new_model):
        """Handle when the electrodes model changes."""

        # Trigger an update to redraw and re-initialize the svg widget once a new svg file is selected.
        self.window.central_pane.set_view_from_model(new_model)
        logger.debug(f"New Electrode Layer added --> {new_model.svg_model.filename}")

        # Initialize the electrode mouse interaction service with the new model and layer
        self.interaction_service = ElectrodeInteractionControllerService(
            electrodes_model=new_model,
            electrode_view_layer=self.window.central_pane.current_electrode_layer
        )

        # Update the scene with the interaction service
        self.window.central_pane.scene.interaction_service = self.interaction_service

        logger.debug(f"Setting up handlers for new layer for new electrodes model {new_model}")
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(self.electrodes_model.channels_states_map))

    ###########################################################################
    # Menu actions.
    ###########################################################################

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

    ####### handlers for dramatiq listener topics ##########
    def _on_setup_success_triggered(self, message):
        if self.electrodes_model:
            publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(self.electrodes_model.channels_states_map))

# system imports.
import json
import dramatiq

# Enthought library imports.
from pyface.tasks.action.api import SMenu, SMenuBar, TaskToggleGroup, TaskAction
from pyface.tasks.api import PaneItem, Task, TaskLayout, HSplitter, VSplitter
from pyface.api import GUI
from traits.api import Instance, provides

from microdrop_application.views.microdrop_pane import MicrodropCentralCanvas
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase
from microdrop_utils.status_bar_utils import set_status_bar_message
# Local imports.
from .consts import PKG

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_controller_base import (generate_class_method_dramatiq_listener_actor,
                                                      basic_listener_actor_routine)

from dropbot_tools_menu.self_test_dialogs import WaitForTestDialogAction

logger = get_logger(__name__, level="DEBUG")

listener_name = f"{PKG}_listener"


@provides(IDramatiqControllerBase)
class MicrodropTask(Task):
    ##########################################################
    # 'IDramatiqControllerBase' interface.
    ##########################################################

    # Child window should be an instance of Dialog Action
    wait_for_test_dialog = Instance(WaitForTestDialogAction)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    listener_name = f"{PKG}_listener"
    
    #### 'MicrodropTask' interface #########################
    
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

        logger.info("Starting Microdrop listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine)

    #### 'Task' interface #####################################################

    id = f"{PKG}.task"
    name = PKG.title().replace("_", " ")

    menu_bar = SMenuBar(

        SMenu(id="File", name="&File"),

        SMenu(id="Edit", name="&Edit"),

        SMenu(id="Tools", name="&Tools"),

        SMenu(TaskToggleGroup(), id="View", name="&View")
    )

    def create_central_pane(self):
        """Create the central pane with the device viewer widget with a default view.
        """

        return MicrodropCentralCanvas()

    def create_dock_panes(self):
        """Create any dock panes needed for the task."""
        return [
        ]

    def activated(self):
        """Called when the task is activated."""
        pass


    ###########################################################################
    # Protected interface.
    ###########################################################################

    # ------------------ Trait initializers ---------------------------------

    def _default_layout_default(self):

        top_right = HSplitter(
            PaneItem("dropbot_status.dock_pane"),
            PaneItem("manual_controls.dock_pane"),
        )

        right = VSplitter(
            top_right,
            PaneItem("protocol_grid.dock_pane", height=1000),
        )

        return TaskLayout(
            right=right,
            left=PaneItem("device_viewer.dock_pane", width=1000),
        )

    ##########################################################
    # Public interface.
    ##########################################################
    def show_help(self):
        """Show the help dialog."""
        logger.info("Showing help dialog.")

    ##########################################################
    # Including below function permanently this class, so no need to dynamically attach it in dropbot_tools_menu/plugin.py
    # This callback is registered in ACTOR_TOPIC_DICT of dropbot_tools_menu and does nothing if that plugin is not loaded
    # The relevant code has to be here since the dialogs need to be manipulated from the main task
    ##########################################################

    def _on_self_tests_progress_triggered(self, current_message):
        '''
        Method adds on to the device viewer task to listen to the self tests topic and react accordingly
        '''
        message = json.loads(current_message)
        active_state = message.get('active_state')
        current_test_name = message.get('current_test_name')
        current_test_id = message.get('current_test_id')
        total_tests = message.get('total_tests')
        report_path = message.get('report_path')
        cancelled = message.get('cancelled', False)
        
        def show_dialog():
            self.wait_for_test_dialog = WaitForTestDialogAction()
            if total_tests == 1:
                test_name = current_test_name.replace("_", " ").capitalize()
                self.wait_for_test_dialog.perform(self, 
                                                  test_name=test_name)
            else:
                test_name = 'All Tests'
                self.wait_for_test_dialog.perform(self, 
                                                  test_name=test_name, 
                                                  mode="progress_bar")
            
        if current_test_id == 0 and current_test_name is not None:
            # Start child window here when current_test_id == 0
            # Force the dialog to be shown in the next event loop iteration
            GUI.invoke_later(show_dialog)
            
        logger.info(f"Handler called. test_name = {current_test_name}, Running test = {current_test_id} / {total_tests}")

        # Update the progress bar if in progress mode.
        if total_tests > 1:
            if not active_state:
                percentage = 100
            else:
                percentage = int((current_test_id / total_tests) * 100)
                
            logger.debug(f"Progress: {percentage}")
            GUI.invoke_later(self.wait_for_test_dialog.set_progress, 
                             percentage, 
                             current_test_name)

        # Close the dialog when the test is done
        if not active_state:
            GUI.invoke_later(self.wait_for_test_dialog.close)
            if cancelled:
                GUI.invoke_later(set_status_bar_message, "Self test cancelled.", self.window)
            else:
                GUI.invoke_later(set_status_bar_message, "Self test completed.", self.window)
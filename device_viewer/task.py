# system imports.
import json
import os
import dramatiq

# Enthought library imports.
from pyface.tasks.action.api import SMenu, SMenuBar, TaskToggleGroup, TaskAction
from pyface.tasks.api import Task, TaskLayout, Tabbed
from pyface.api import FileDialog, OK
from traits.api import Instance, Str, provides

from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase
# Local imports.
from .models.electrodes import Electrodes
from .views.device_view_pane import DeviceViewerPane
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from .consts import ELECTRODES_STATE_CHANGE
from .services.electrode_interaction_service import ElectrodeInteractionControllerService
from .consts import PKG

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor, \
    basic_listener_actor_routine

logger = get_logger(__name__, level="DEBUG")
DEFAULT_SVG_FILE = f"{os.path.dirname(__file__)}{os.sep}2x3device.svg"

listener_name = f"{PKG}_listener"

from dropbot_tools_menu.menus import ProgressBar, ALL_TESTS
import threading
from dropbot_tools_menu.menus import parse_test_voltage_html_report, parse_on_board_feedback_calibration_html_report, parse_scan_test_board_html_report
from dropbot_tools_menu.self_test_dialogs import ResultsDialog, SelfTestIntroDialog, ScanTestBoardResultsDialog
# from PySide6 import Qt

@provides(IDramatiqControllerBase)
class DeviceViewerTask(Task):
    ##########################################################
    # 'IDramatiqControllerBase' interface.
    ##########################################################
    # for debugging purposes
    last_test_mode = Str("individual")  # or 'all'
    # TODO: Child window should be an instance of DeviceViewerTask
    # i.e., child_window = Instance(DeviceViewerTask)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    listener_name = f"{PKG}_listener"

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

    id = f"{PKG}.task"
    name = PKG.title().replace("_", " ")

    menu_bar = SMenuBar(

        SMenu(
            TaskAction(id="open_svg_file", name='&Open SVG File', method='open_file_dialog', accelerator='Ctrl+O'),
            id="File", name="&File"
        ),

        SMenu(id="Edit", name="&Edit"),

        SMenu(id="Tools", name="&Tools"),

        SMenu(TaskToggleGroup(), id="View", name="&View")
    )

    def create_central_pane(self):
        """Create the central pane with the device viewer widget with a default view.
        """

        return DeviceViewerPane(electrodes=self.electrodes_model)

    def create_dock_panes(self):
        """Create any dock panes needed for the task."""
        return [
        ]

    def activated(self):
        """Called when the task is activated."""
        logger.debug(f"Device Viewer Task activated. Setting default view with {DEFAULT_SVG_FILE}...")
        _electrodes = Electrodes()
        _electrodes.set_electrodes_from_svg_file(DEFAULT_SVG_FILE)

        self.electrodes_model = _electrodes

    #### 'DeviceViewerTask' interface ##########################################

    electrodes_model = Instance(Electrodes)

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
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(self.electrodes_model.channels_states_map))

    ##########################################################
    # Public interface.
    ##########################################################
    def show_help(self):
        """Show the help dialog."""
        logger.info("Showing help dialog.")

    ##########################################################
    # Including below function permanently this class, so no need to dynamically attach it in dropbot_tools_menu/plugin.py
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
        # active_state = message.get('active_state')
        # current_message = message.get('current_message')
        # done_test_number = message.get('done_test_number')
        # report_path = message.get('report_path')
        # test_name = message.get('test_name')x
        
       
        if current_test_id == 0:
             # TODO: start child window here when current_test_id == 0
            # i.e., self.make_child_window()
            pass
        
        current_test_id += 1
        
        logger.info(f"Handler called. test_name = {current_test_name}, Running test = {current_test_id} / {total_tests}")
        
        # print(current_message, threading.current_thread().name)
        
        # if self.progress_bar is not None:
        if not active_state:
            # TODO: Progress bar should be part of the child window and the message should be an attribute of the child window
            # self.progress_bar.current_message = "Done running all tests. Generating report...\n"
            pass
        else:
            # TODO: Progress bar should be part of the child window and the message should be an attribute of the child window
            # self.progress_bar.current_message = f"Processing: {current_test_name}\n"
            pass
        
        # sort sleep to update the progress bar
        if current_test_id is not None:
            percentage = int((current_test_id / total_tests) * 100)
            logger.debug(f"Progress: {percentage}")
            # TODO: Progress bar should be part of the child window and the message should be an attribute of the child window
            # self.progress_bar.progress = percentage

        if not active_state and report_path :
            # TODO: Close child window here when all tests are done
            # i.e., self.close_child_window()
        elif not active_state and report_path is None:
            # TODO: Close child window here when all tests are done and create a new one with the report
            # i.e., self.close_child_window()
            
            # open_html_in_browser(report_path)
            # close progress bar
            # if hasattr(self, "progress_bar_ui") and self.progress_bar_ui is not None:
            #     self.progress_bar_ui.dispose()
            #     self.progress_bar_ui = None
            # self.progress_bar = None

            # show report on html or on results dialog depending on last_test_mode
            # Handle results for each individual test by name
            # if getattr(self, 'last_test_mode', 'individual') == "individual":
            #     if test_name == 'test_voltage':
            #         parsed_data = parse_test_voltage_html_report(report_path)
            #         dialog = ResultsDialog(
            #             parent=None,
            #             table_data=parsed_data.get('table'),
            #             rms_error=parsed_data.get('rms_error'),
            #             plot_data=parsed_data.get('plot_data')
            #         )
            #     elif test_name == 'test_on_board_feedback_calibration':
            #         parsed_data = parse_on_board_feedback_calibration_html_report(report_path)
            #         dialog = ResultsDialog(
            #             parent=None,
            #             table_data=parsed_data.get('table'),
            #             rms_error=None,
            #             plot_data=parsed_data.get('plot_data')
            #         )
            #     elif test_name == 'test_channels':
            #         parsed_data = parse_scan_test_board_html_report(report_path)
            #         dialog = ScanTestBoardResultsDialog(
            #             parent=None,
            #             description_text=parsed_data.get('description_text', ''),
            #             images=parsed_data.get('images', [])
            #         )                       
            #     else:
            #         # add other individual tests here
            #         return
            #     dialog.exec_()
            # elif getattr(self, 'last_test_mode', 'all') == "all":
            #     open_html_in_browser(report_path)


class ProgressBar(HasTraits):
    """A TraitsUI application with a progress bar."""

    current_message = Str()
    progress = Int(0)
    num_tasks = Int(1)

    def _progress_default(self):
        return 0

    def _num_tasks_default(self):
        return 1

    traits_view = View(
        HGroup(
            UItem(
                "progress",
                editor=ProgressEditor(
                    message_name="current_message", 
                    min_name="progress", 
                    max_name="num_tasks",
                ),
            ),
        ),
        title="Running Dropbot On-board Self-tests...",
        resizable=True,
        width=400,
        height=100
    )


class MakeChildWindow(HasTraits):
    def __init__(self, parent=None):
        self.parent = parent

    def make_child_window(self):
        pass
    
    def create_child_window(self):
        # set test mode separately
        if self.num_tests == len(ALL_TESTS):
            task.last_test_mode = "all"         
        else:
            task.last_test_mode = "individual"

        app = QtWidgets.QApplication.instance()
        parent_window = app.topLevelWidgets()[0] if app and app.topLevelWidgets() else None
        intro_dialog = SelfTestIntroDialog(parent=parent_window)
        result = intro_dialog.exec_()
        if result != QtWidgets.QDialog.Accepted:
            return
        
        # progress bar
        if not hasattr(task, "progress_bar") or task.progress_bar is None:
            task.progress_bar = ProgressBar(num_tasks=self.num_tests)
            # task.progress_bar_ui = self.progress_bar.edit_traits()
        else:
            task.progress_bar.num_tasks = self.num_tests
        task.progress_bar.progress = 0
        task.progress_bar.current_message = "Starting...\n"

        # show progress bar
        task.progress_bar_ui = task.progress_bar.edit_traits()        

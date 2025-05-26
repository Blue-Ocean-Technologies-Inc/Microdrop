from dropbot.hardware_test import ALL_TESTS
from pyface.tasks.action.api import SMenu, TaskWindowAction
from traits.api import Property, Directory

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from dropbot_controller.consts import RUN_ALL_TESTS, TEST_SHORTS, TEST_VOLTAGE, TEST_CHANNELS, \
    TEST_ON_BOARD_FEEDBACK_CALIBRATION, START_DEVICE_MONITORING

from traits.api import HasTraits, Str, Int, Any
from traitsui.editors.progress_editor import ProgressEditor
from traitsui.api import View, HGroup, UItem

from .consts import PKG

#new
from .self_test_dialogs import SelfTestIntroDialog, ResultsDialog
from PySide6 import QtWidgets
from dropbot_controller.consts import SELF_TESTS_PROGRESS
import json
from bs4 import BeautifulSoup #html parser

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
                    max_name="num_tasks"
                ),
            ),
        ),
        title="Running Dropbot On-board Self-tests...",
        resizable=True,
        width=400,
        height=100
    )

class DramatiqMessagePublishAction(TaskWindowAction):
    topic = Str(desc="topic this action connects to")
    message = Any(desc="message to publish")

    def perform(self, event=None):
        publish_message(topic=self.topic, message=self.message)


class RunTests(DramatiqMessagePublishAction):
    num_tests = Int(1, desc="number of tests run")
    message = Property(Directory, observe="object.application.app_data_dir")

    def _get_message(self):
        if self.object.application:
            return self.object.application.app_data_dir
        return None

    def perform(self, event=None):
        logger.info("Requesting running self tests for dropbot")

        #super().perform(event)

        # referencing to DeviceViewerTask instance
        task = getattr(self, "task", None)
        if task is None:
            logger.error("Cannot find DeviceViewerTask instance.")
            return

        if self.num_tests == len(ALL_TESTS): # running all tests
            task.last_test_mode = "all" # for debugging only
            logger.info("Set last_test_mode to 'all'")
            # intro dialog box 
            app = QtWidgets.QApplication.instance()
            parent_window = app.topLevelWidgets()[0] if app and app.topLevelWidgets() else None
            intro_dialog = SelfTestIntroDialog(parent=parent_window)
            result = intro_dialog.exec_()
            if result != QtWidgets.QDialog.Accepted:
                return
            
            # progress bar
            if not hasattr(task, "progress_bar") or task.progress_bar is None:
                task.progress_bar = ProgressBar(num_tasks=len(ALL_TESTS))
                # task.progress_bar_ui = self.progress_bar.edit_traits()
            else:
                task.progress_bar.num_tasks = len(ALL_TESTS)
            task.progress_bar.progress = 0
            task.progress_bar.current_message = "Starting...\n"

            super().perform(event)

            # show progress bar
            task.progress_bar.edit_traits()
            # task.progress_bar_ui = self.progress_bar.edit_traits()
            
            # results handled in update handler (will open report of all tests in browser)

        else: # individual test
            task.last_test_mode = "individual" # for debugging only
            logger.info("Set last_test_mode to 'individual'")
            super().perform(event)

def dropbot_tools_menu_factory():
    """
    Create a menu for the Manual Controls
    The Sgroup is a list of actions that will be displayed in the menu.
    In this case there is only one action, the help menu.
    It is contributed to the manual controls dock pane using its show help method. Hence it is a DockPaneAction.
    It fetches the specified method from the dock pane essentially.
    """

    # create new groups with all the possible dropbot self-test options as actions
    test_actions = [
        RunTests(name="Test high voltage", topic=TEST_VOLTAGE),
        RunTests(name='On-board feedback calibration', topic=TEST_ON_BOARD_FEEDBACK_CALIBRATION),
        RunTests(name='Detect shorted channels', topic=TEST_SHORTS),
        RunTests(name="Scan test board", topic=TEST_CHANNELS),
    ]

    test_options_menu = SMenu(items=test_actions, id="dropbot_on_board_self_tests", name="On-board self-tests", )

    # create an action to run all the test options at once
    run_all_tests = RunTests(name="Run all on-board self-tests", topic=RUN_ALL_TESTS, num_tests=len(ALL_TESTS))

    '''
    (from hardware_test.py)
    ALL_TESTS = ['system_info', 'test_system_metrics', 'test_i2c', 'test_voltage',
             'test_shorts', 'test_on_board_feedback_calibration',
             'test_channels']
    '''

    # create an action to restart dropbot search
    dropbot_search = DramatiqMessagePublishAction(name="Search for Dropbot Connection", topic=START_DEVICE_MONITORING)

    # return an SMenu object compiling each object made and put into Dropbot menu under Tools menu.
    return SMenu(items=[run_all_tests, test_options_menu, dropbot_search], id="dropbot_tools", name="Dropbot")


def parse_html_report(html_path):
    """
    Parse the test voltage report and return a dictionary of the results.
    """
    with open(html_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    # extract JSON results from the <script id="results"> tag
    script_tag = soup.find('script', {'id': 'results'})
    if not script_tag:
        raise ValueError("No <script id='results'> tag found in the HTML report.")
    
    json_data = json.loads(script_tag.string)

    # extract test voltage results for specific parsing
    voltage_results = json_data.get("test_voltage", {})
    table = []
    if 'target_voltage' in voltage_results and 'measured_voltage' in voltage_results:
        target_voltages = voltage_results['target_voltage']['__ndarray__']
        measured_voltages = voltage_results['measured_voltage']

        # create a table-like structure
        table = ['Target Voltage', 'Measured Voltage']
        for t, m in zip(target_voltages, measured_voltages):
            table.append([f'{t:.2f}', f'{m:.2f}'])

   

    # rms error
    rms_error = voltage_results.get('rms_error', None)

    # plot data
    plot_data = { 
        "x": voltage_results.get("target_voltage", {}).get("__ndarray__", []),
        "y": voltage_results.get("measured_voltage", [])
    }

    return {
        "table": table,
        "rms_error": rms_error,
        "plot_data": plot_data
    }
        
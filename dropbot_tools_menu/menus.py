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
from .self_test_intro_dialog import SelfTestIntroDialog

from PySide6 import QtWidgets


from dropbot_controller.consts import SELF_TESTS_PROGRESS

class ProgressBar(HasTraits):
    """A TraitsUI application with a progress bar."""

    current_message = Str()
    progress = Int(0)
    num_tasks = Int(1)

    traits_view = View(
        HGroup(
            UItem(
                "progress",
                editor=ProgressEditor(message_name="current_message", min_name="progress", max_name="num_tasks")
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

        ##intro dialog box with images        
        app = QtWidgets.QApplication.instance()
        parent_window = app.topLevelWidgets()[0] if app and app.topLevelWidgets() else None
        intro_dialog = SelfTestIntroDialog(parent=parent_window)
        result = intro_dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            super().perform(event)
            return
        
        
            
           


        
        

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

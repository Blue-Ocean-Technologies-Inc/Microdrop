from dropbot.hardware_test import ALL_TESTS
from pyface.tasks.action.api import SMenu, TaskWindowAction
from traits.api import Property, Directory

from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.status_bar_utils import set_status_bar_message

from dropbot_controller.consts import RUN_ALL_TESTS, TEST_SHORTS, TEST_VOLTAGE, TEST_CHANNELS, \
    TEST_ON_BOARD_FEEDBACK_CALIBRATION, START_DEVICE_MONITORING
from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

from traits.api import Str, Int, Any, Bool

from .consts import PKG

from .self_test_dialogs import ShowSelfTestIntroDialogAction, DropbotDisconnectedDialogAction



class DramatiqMessagePublishAction(TaskWindowAction):
    topic = Str(desc="topic this action connects to")
    message = Any(desc="message to publish")

    def perform(self, event=None):
        publish_message(topic=self.topic, message=self.message)



class RunTests(DramatiqMessagePublishAction):
    num_tests = Int(1, desc="number of tests run")
    message = Property(Directory, observe="object.application.app_data_dir")
    plugin = Any()

    def _get_message(self, event = None):
        # if event and hasattr(event, "task") and hasattr(event.task, "application"):
        #     return event.task.application.app_data_dir
        if self.object and hasattr(self.object, "application"):
            return self.object.application.app_data_dir
        return None

    def perform(self, event=None):
        window = getattr(event, "task", None)
        if window is not None and hasattr(window, "window"):
            window = window.window
        else:
            window = None

        dropbot_connected = self.plugin.dropbot_connected
        if not dropbot_connected:
            set_status_bar_message("Warning: Cannot start test, Dropbot is disconnected", window)
            disconnected_dialog = DropbotDisconnectedDialogAction()
            return disconnected_dialog.perform(event)

        logger.info("Requesting running self tests for dropbot")
        self_test_intro_dialog = ShowSelfTestIntroDialogAction()
      
        # only show the intro dialog for the tests that require the test board
        if self.topic != TEST_VOLTAGE and self.topic != TEST_ON_BOARD_FEEDBACK_CALIBRATION:
            set_status_bar_message("Click OK to continue", window)
            if self_test_intro_dialog.perform(event):
                set_status_bar_message("Running self tests...", window, 15000)
                super().perform(event)
        else:
            set_status_bar_message("Running self tests...", window, 30000)
            super().perform(event)


def dropbot_tools_menu_factory(plugin=None):
    """
    Create a menu for the Manual Controls
    The Sgroup is a list of actions that will be displayed in the menu.
    In this case there is only one action, the help menu.
    It is contributed to the manual controls dock pane using its show help method. Hence it is a DockPaneAction.
    It fetches the specified method from the dock pane essentially.
    """

    # create new groups with all the possible dropbot self-test options as actions
    test_actions = [
        RunTests(name="Test high voltage", topic=TEST_VOLTAGE,  plugin=plugin),
        RunTests(name='On-board feedback calibration', topic=TEST_ON_BOARD_FEEDBACK_CALIBRATION, plugin=plugin),
        RunTests(name='Detect shorted channels', topic=TEST_SHORTS,  plugin=plugin),
        RunTests(name="Scan test board", topic=TEST_CHANNELS, plugin=plugin),
    ]

    test_options_menu = SMenu(items=test_actions, id="dropbot_on_board_self_tests", name="On-board self-tests", )

    # create an action to run all the test options at once
    run_all_tests = RunTests(name="Run all on-board self-tests", topic=RUN_ALL_TESTS, num_tests=len(ALL_TESTS), plugin=plugin)

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



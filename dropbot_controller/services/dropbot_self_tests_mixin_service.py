import json
from pathlib import Path
from functools import wraps
from tqdm import tqdm
# ******************************** DO NOT remove unused imports here **************************************
from dropbot.hardware_test import (ALL_TESTS, system_info, test_system_metrics,
                                   test_i2c, test_voltage, test_shorts,
                                   test_on_board_feedback_calibration,
                                   test_channels)
# **********************************************************************************************************

from dropbot.self_test import (generate_report, plot_test_voltage_results, 
                               plot_test_on_board_feedback_calibration_results, 
                               plot_test_channels_results)
from traits.api import provides, HasTraits, Str, Instance

from microdrop_utils.datetime_helpers import get_current_utc_datetime
from microdrop_utils.file_handler import open_html_in_browser
from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import SHORTS_DETECTED

from ..consts import SELF_TESTS_PROGRESS, TestEvent, create_test_progress_message

from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService


from pyface.api import GUI

from dropbot_tools_menu.self_test_dialogs import ResultsDialogAction

logger = get_logger(__name__)


def get_timestamped_results_path(test_name: str, path: [str, Path]) -> Path:
    """
    Simple function to add datestamp to a given path
    """

    if not isinstance(path, Path):
        path = Path(path)

    # Generate unique filename
    timestamp = get_current_utc_datetime()

    return path.joinpath(f'{test_name}_results-{timestamp}')


class TestSession:
    def __init__(self, total_tests, report_path=None, tests=None):
        self.total_tests = total_tests
        self.report_path = report_path
        self.tests = tests

    def __enter__(self):
        # Notify UI to Open Dialog IMMEDIATELY
        publish_message(
            topic=SELF_TESTS_PROGRESS,
            message=create_test_progress_message(
                TestEvent.SESSION_START,
                total_tests=self.total_tests,
                report_path=self.report_path,
                tests=self.tests
            ),
        )
        return self

    def update(self, test_name, test_index):
        # Notify UI of Progress
        publish_message(
            topic=SELF_TESTS_PROGRESS,
            message=create_test_progress_message(
                TestEvent.PROGRESS, test_name=test_name, test_index=test_index
            ),
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Automatically runs when the loop finishes OR crashes
        status = "cancelled" if exc_type is KeyboardInterrupt else "completed"
        publish_message(
            topic=SELF_TESTS_PROGRESS, message=create_test_progress_message(TestEvent.SESSION_END, status=status)
        )

@provides(IDropbotControlMixinService)
class DropbotSelfTestsMixinService(HasTraits):
    """
    A mixin Class that adds methods to set states for a dropbot connection and get some dropbot information.
    """

    id = Str("dropbot_self_tests_mixin_service")
    name = Str('Dropbot Self Tests Mixin')
    results_dialog = Instance(ResultsDialogAction)

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self._self_test_cancelled = False

    def cancel_self_test(self):
        self._self_test_cancelled = True
         
    ######################################## private methods ##############################################

    @staticmethod
    def _execute_test_based_on_name(func):
        @wraps(func)
        def _execute_test(self, report_generation_directory):
            """
            Method to execute a dropbot test based on the name
            """
            # find the required test name based on the dropbot function name see dropbot.hardware_test
            test_name = "_".join(func.__name__.split('_')[1:-1])

            # set the report file name in the needed dir based on tests run
            report_path = get_timestamped_results_path(test_name, report_generation_directory).with_suffix('.html')
            report_path = str(report_path.absolute())

            # the tests arg should be None for self test if all tests need to be run
            if test_name == "run_all_tests":
                tests = None
            else:
                tests = [test_name]
                report_path = None

            logger.info(f"Running test: {test_name}, with output path in: {report_path}")
            self._self_test_cancelled = False
            with self.proxy.signals.signal('shorts-detected').muted():
                result = self._self_test(self.proxy, tests=tests, report_path=report_path)

            if report_path is not None:
                logger.info(f"Report generating in the file {report_path}")
                generate_report(result, report_path, force=True)
                open_html_in_browser(report_path)
            elif self._self_test_cancelled:
                logger.info("Self-test was cancelled, skipping report and result dialog.")
            else:
                plot_data = None
                if test_name == "test_voltage":
                    plot_data = plot_test_voltage_results(result[test_name], 
                                                        return_fig=True)
                elif test_name == "test_on_board_feedback_calibration":
                    plot_data = plot_test_on_board_feedback_calibration_results(result[test_name], 
                                                                                return_fig=True)
                elif test_name == "test_channels":
                    plot_data = plot_test_channels_results(result[test_name], 
                                                        return_fig=True)

                if plot_data is not None:
                    # Pull up the report in a window
                    def show_results_dialog():
                        self.results_dialog = ResultsDialogAction()
                        test_name_display = test_name.replace("_", " ").capitalize() + " Results"
                        self.results_dialog.perform(title=test_name_display, 
                                                    plot_data=plot_data)
                    GUI.invoke_later(show_results_dialog)
                else:
                    shorts_dict = {'Shorts_detected': result[test_name]['shorts'], 
                                   'Show_window': True}
                    publish_message(topic=SHORTS_DETECTED, message=json.dumps(shorts_dict))
                    pass

            # do whatever else is defined in func
            func(self, report_generation_directory)  
        return _execute_test

    def _self_test(self, proxy, tests=None, report_path=None):
        """
        .. versionadded:: 1.28

        Perform quality control tests.

        Parameters
        ----------
        proxy : dropbot.SerialProxy
            DropBot control board reference.
        tests : list, optional
            List of names of test functions to run.

            By default, run all tests.

        Returns
        -------
        dict
            Results from all tests.
        """
        total_time = 0

        if tests is None:
            tests = ALL_TESTS

        results = {}

        # The 'with' block handles Open/Close of the UI automatically
        with TestSession(len(tests), report_path, tests) as session:

            # Safe function lookup (No eval!)
            test_funcs = [
                (name, globals().get(name)) for name in tests if globals().get(name)
            ]

            for i, (name, func) in enumerate(pbar := tqdm(test_funcs)):
                if self._self_test_cancelled:
                    logger.warning("Self-test sequence cancelled by user.")
                    break

                try:
                    # 1. Log START of test
                    logger.info(f"Running test [{i+1}/{len(test_funcs)}]: {name}")

                    session.update(name, i)  # Send Progress
                    pbar.set_description(name)

                    # Run the test function
                    result = func(proxy)
                    results[name] = result

                    # 2. Log RESULT of test
                    logger.info(f"Test '{name}' completed. Result: {result}")

                except Exception as e:
                    logger.error(f"Test '{name}' failed with exception: {e}", exc_info=True)
                    results[name] = "ERROR"

        return results

    ######################################## Methods to Expose #############################################

    @_execute_test_based_on_name
    def on_run_all_tests_request(self, report_generation_directory: str):
        """
        Method to run all dropbot hardware tests
        """
        pass

    @_execute_test_based_on_name
    def on_test_voltage_request(self, report_generation_directory: str):
        """
        Method to run the high voltage dropbot test
        """
        pass

    @_execute_test_based_on_name
    def on_test_on_board_feedback_calibration_request(self, report_generation_directory: str):
        """
        Method to run the On-Board feedback calibration test.
        """
        pass

    @_execute_test_based_on_name
    def on_test_shorts_request(self, report_generation_directory: str):
        """
        Method to run the shorted channels test.
        """
        pass

    @_execute_test_based_on_name
    def on_test_channels_request(self, report_generation_directory: str):
        """
        Method to run the test board scan.
        """
        pass

    def on_self_test_cancel_request(self, message):
        """
        Method to cancel the self test
        """
        logger.info("Self test cancelled by user.")
        self.cancel_self_test()

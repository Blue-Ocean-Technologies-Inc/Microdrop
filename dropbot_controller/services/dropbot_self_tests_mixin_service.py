import json
from pathlib import Path
from functools import wraps
import datetime as dt
from tqdm import tqdm

from dropbot.hardware_test import (ALL_TESTS, system_info, test_system_metrics,
                                   test_i2c, test_voltage, test_shorts,
                                   test_on_board_feedback_calibration,
                                   test_channels)

from dropbot.self_test import (generate_report, plot_test_voltage_results, 
                               plot_test_on_board_feedback_calibration_results, 
                               plot_test_channels_results)
from traits.api import provides, HasTraits, Str, Instance

from microdrop_utils.file_handler import open_html_in_browser
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ..consts import SELF_TESTS_PROGRESS

from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService


from pyface.api import GUI

from dropbot_tools_menu.self_test_dialogs import ResultsDialogAction

logger = get_logger(__name__, level="DEBUG")


def get_timestamped_results_path(test_name: str, path: [str, Path]) -> Path:
    """
    Simple function to add datestamp to a given path
    """

    if not isinstance(path, Path):
        path = Path(path)

    # Generate unique filename
    timestamp = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H_%M_%S')

    return path.joinpath(f'{test_name}_results-{timestamp}')


def _self_test(proxy, tests=None, report_path=None):
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

    stuctured_message = {"active_state": True, "current_test_name": None, 
                         "current_test_id": 0, "total_tests": len(tests), 
                         "report_path": report_path }

    for i, test_name_i in enumerate(pbar := tqdm(tests)):
        # description of test that will be processed
        stuctured_message["current_test_name"] = test_name_i
        stuctured_message["current_test_id"] = i
        pbar.set_description(test_name_i)
        
        # publish the job
        publish_message(topic=SELF_TESTS_PROGRESS, message=json.dumps(stuctured_message))
        
        # do the job
        test_func_i = eval(test_name_i)
        results[test_name_i] = test_func_i(proxy)

        duration_i = results[test_name_i]['duration']
        logger.debug('%s: %.1f s', test_name_i, duration_i)
        total_time += duration_i

    stuctured_message["active_state"] = False
    stuctured_message["current_test_name"] = None
    publish_message(topic=SELF_TESTS_PROGRESS, message=json.dumps(stuctured_message))

    logger.info('**Total time: %.1f s**', total_time)

    return results


@provides(IDropbotControlMixinService)
class DropbotSelfTestsMixinService(HasTraits):
    """
    A mixin Class that adds methods to set states for a dropbot connection and get some dropbot information.
    """

    id = Str("dropbot_self_tests_mixin_service")
    name = Str('Dropbot Self Tests Mixin')
    results_dialog = Instance(ResultsDialogAction)
    
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
            result = _self_test(self.proxy, tests=tests, report_path=report_path)

            logger.info(f"Report generating in the file {report_path}")
            generate_report(result, report_path, force=True)
            
            if report_path is not None:
                open_html_in_browser(report_path)
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
                    # TODO: show the result of short test
                    pass

            # do whatever else is defined in func
            func(self, report_generation_directory)

        return _execute_test

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

import json
from pathlib import Path
from functools import wraps
import datetime as dt
from tqdm import tqdm

from dropbot.hardware_test import (ALL_TESTS, system_info, test_system_metrics,
                                   test_i2c, test_voltage, test_shorts,
                                   test_on_board_feedback_calibration,
                                   test_channels)

from dropbot.self_test import generate_report
from traits.api import provides, HasTraits

from microdrop_utils.file_handler import open_html_in_browser
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ..consts import SELF_TESTS_PROGRESS

logger = get_logger(__name__)

from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService


def get_timestamped_results_path(test_name: str, path: [str, Path]):
    """
    Simple function to add datestamp to a given path
    """

    if not isinstance(path, Path):
        path = Path(path)

    # Generate unique filename
    timestamp = dt.datetime.utcnow().strftime('%Y-%m-%dT%H_%M_%S')

    return path.joinpath(f'{test_name}_results-{timestamp}')


def self_test(proxy, tests=None):
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

    publish_message(topic=SELF_TESTS_PROGRESS, message=json.dumps({"active_state": True}))

    for i, test_name_i in enumerate(pbar := tqdm(tests)):
        # description of test that will be processed
        publish_message(topic=SELF_TESTS_PROGRESS, message=json.dumps({"current_message": test_name_i}))
        pbar.set_description(test_name_i)

        # do the job
        test_func_i = eval(test_name_i)
        results[test_name_i] = test_func_i(proxy)

        # job done
        publish_message(topic=SELF_TESTS_PROGRESS, message=json.dumps({"done_test_number": i}))

        duration_i = results[test_name_i]['duration']
        logger.info('%s: %.1f s', test_name_i, duration_i)
        total_time += duration_i

    publish_message(topic=SELF_TESTS_PROGRESS, message=json.dumps({"active_state": False}))

    logger.info('**Total time: %.1f s**', total_time)

    return results


@provides(IDropbotControlMixinService)
class DropbotSelfTestsMixinService(HasTraits):
    """
    A mixin Class that adds methods to set states for a dropbot connection and get some dropbot information.
    """

    id = "dropbot_self_tests_mixin_service"
    name = 'Dropbot Self Tests Mixin'

    ######################################## private methods ##############################################

    @staticmethod
    def _execute_test_based_on_name(func):
        @wraps(func)
        def _execute_test(self, report_generation_directory):
            """
            Method to execute a dropbot test based on the name
            """

            # find the required test name based on the function name "on_testname_request"
            test_name = "_".join(func.__name__.split('_')[1:-1])

            # set the report file name in the needed dir based on tests run
            report_path = f"{get_timestamped_results_path(test_name, report_generation_directory)}.html"

            # the tests arg should be None for self test if all tests need to be run
            if test_name == "run_all_tests":
                tests = None
            else:
                tests = [test_name]

            logger.info(f"Running test {test_name}")
            result = self_test(self.proxy, tests=tests)

            logger.info(f"Report generating in the file {report_path}")
            generate_report(result, report_path, force=True)
            publish_message(topic=SELF_TESTS_PROGRESS, message=json.dumps({"report_path": report_path, "test_name": test_name}))

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

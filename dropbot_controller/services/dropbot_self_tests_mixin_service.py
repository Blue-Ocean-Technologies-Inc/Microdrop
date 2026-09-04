# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json
from functools import wraps
from pathlib import Path

# Third-party imports.
import numpy as np

# ********************* DO NOT remove unused imports here **********************
from dropbot.hardware_test import (  # noqa: F401
    ALL_TESTS,
    system_info,
    test_channels,
    test_i2c,
    test_on_board_feedback_calibration,
    test_shorts,
    test_system_metrics,
    test_voltage,
)

# ******************************************************************************
from dropbot.self_test import generate_report
from tqdm import tqdm

# Enthought library imports.
from traits.api import HasTraits, Str, provides

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import get_current_utc_datetime
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.file_handler import open_html_in_browser

# Local imports.
from ..consts import (
    SELF_TESTS_PROGRESS,
    self_test_results_publisher,
    shorts_detected_publisher,
)
from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from ..models.self_tests import (
    TestEvent,
    create_test_progress_message,
    serialise_test_results,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

# Tests whose results are published on SELF_TESTS_RESULTS for interactive
# frontend plotting (#611); `test_shorts` and `run_all_tests` are handled
# separately below (shorts_detected_publisher / the full HTML report).
PLOTTABLE_SELF_TESTS = frozenset(
    ("test_voltage", "test_on_board_feedback_calibration", "test_channels")
)


def get_timestamped_results_path(test_name: str, path: [str, Path]) -> Path:
    """
    Simple function to add datestamp to a given path
    """

    if not isinstance(path, Path):
        path = Path(path)

    # Generate unique filename
    timestamp = get_current_utc_datetime()

    return path.joinpath(f"{test_name}_results-{timestamp}")


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
                tests=self.tests,
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
            topic=SELF_TESTS_PROGRESS,
            message=create_test_progress_message(TestEvent.SESSION_END, status=status),
        )


@provides(IDropbotControlMixinService)
class DropbotSelfTestsMixinService(HasTraits):
    """
    A mixin Class that adds methods to set states for a dropbot connection
    and get some dropbot information.
    """

    id = Str("dropbot_self_tests_mixin_service")
    name = Str("Dropbot Self Tests Mixin")

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self._self_test_cancelled = False

    def cancel_self_test(self):
        self._self_test_cancelled = True

    ################################# private methods ##################################

    @staticmethod
    def _execute_test_based_on_name(func):
        @wraps(func)
        def _execute_test(self, report_generation_directory):
            """
            Method to execute a dropbot test based on the name
            """
            # find the required test name based on the dropbot function
            # name see dropbot.hardware_test
            test_name = "_".join(func.__name__.split("_")[1:-1])

            # set the report file name in the needed dir based on tests run
            report_path = get_timestamped_results_path(
                test_name, report_generation_directory
            ).with_suffix(".html")
            report_path = str(report_path.absolute())

            # the tests arg should be None for self test if all tests need to be run
            if test_name == "run_all_tests":
                tests = None
            else:
                tests = [test_name]
                report_path = None

            logger.info(
                f"Running test: {test_name}, with output path in: {report_path}"
            )
            self._self_test_cancelled = False
            with self.proxy.signals.signal("shorts-detected").muted():
                result = self._self_test(
                    self.proxy, tests=tests, report_path=report_path
                )

            if report_path is not None:
                logger.info(f"Report generating in the file {report_path}")
                generate_report(result, report_path, force=True)
                open_html_in_browser(report_path)
            elif self._self_test_cancelled:
                logger.info(
                    "Self-test was cancelled, skipping report and result dialog."
                )
            elif test_name in PLOTTABLE_SELF_TESTS:
                failed_channels = None
                if test_name == "test_channels":
                    c = np.array(result[test_name]["c"])
                    test_channels_list = result[test_name]["test_channels"]
                    failed_channels = [
                        test_channels_list[i]
                        for i in range(c.shape[0])
                        if np.mean(c[i]) < 5e-12
                    ]

                # Persist the raw results next to the HTML report and publish
                # the file path — the backend stays Qt-free, and the frontend
                # (dropbot_tools_menu, via the microdrop task) reads the file
                # back and renders it interactively via
                # dropbot.self_test.plot_* (#611).
                results_path = get_timestamped_results_path(
                    f"{test_name}_results", report_generation_directory
                ).with_suffix(".json")
                with open(results_path, "w", encoding="utf-8") as results_file:
                    json.dump(serialise_test_results(result[test_name]), results_file)
                logger.info(f"Saved {test_name} self-test results to {results_path}")

                test_name_display = (
                    test_name.replace("_", " ").capitalize() + " Results"
                )
                self_test_results_publisher.publish(
                    test_name=test_name,
                    title=test_name_display,
                    results_path=str(results_path.absolute()),
                    failed_channels=failed_channels,
                )
            else:
                # The user ran the shorts test, so always report back — even
                # when there is nothing to report.
                shorts_detected_publisher.publish(
                    shorted_channels=result[test_name]["shorts"], show_window=True
                )

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
                    logger.info(f"Running test [{i + 1}/{len(test_funcs)}]: {name}")

                    session.update(name, i)  # Send Progress
                    pbar.set_description(name)

                    # Run the test function
                    result = func(proxy)
                    results[name] = result

                    # 2. Log RESULT of test
                    logger.info(f"Test '{name}' completed. Result: {result}")

                except Exception as e:
                    logger.error(
                        f"Test '{name}' failed with exception: {e}", exc_info=True
                    )
                    results[name] = "ERROR"

        return results

    ################################ Methods to Expose #################################

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
    def on_test_on_board_feedback_calibration_request(
        self, report_generation_directory: str
    ):
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

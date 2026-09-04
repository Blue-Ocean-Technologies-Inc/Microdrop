# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Message schemas for the SELF_TESTS_PROGRESS and SELF_TESTS_RESULTS topics.

The dropbot controller owns both topics; the frontend task and the mock
controller import these as the pub/sub payload contract (sanctioned
cross-plugin message-schema import).
"""

# Standard library imports.
import json
from typing import Optional

# Third-party imports.
import numpy as np
from pydantic import BaseModel, StrictInt, StrictStr

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class TestEvent:
    SESSION_START = "SESSION_START"
    PROGRESS = "PROGRESS"
    SESSION_END = "SESSION_END"
    ERROR = "ERROR"


def create_test_progress_message(event_type, **kwargs):
    """Helper to ensure consistent message structure"""
    return json.dumps({"type": event_type, "payload": kwargs})


def serialise_test_results(results):
    """Recursively convert a dropbot self-test result to JSON-native types.

    `numpy` arrays become nested lists (``.tolist()``) and `numpy` scalars
    become Python scalars (``.item()``); dicts, lists and tuples are walked
    recursively; every other value passes through unchanged. Used to write
    a `dropbot.hardware_test` result dict to the JSON file the
    ``SELF_TESTS_RESULTS`` payload points to.
    """
    if isinstance(results, np.ndarray):
        return results.tolist()
    if isinstance(results, np.generic):
        return results.item()
    if isinstance(results, dict):
        return {key: serialise_test_results(value) for key, value in results.items()}
    if isinstance(results, (list, tuple)):
        return [serialise_test_results(value) for value in results]
    return results


def restore_test_results(results):
    """Restore the array-valued fields of a deserialised results dict.

    Inverse of `serialise_test_results` for the flat-dict-of-scalars-and-
    arrays shape the `dropbot.self_test.plot_*` helpers expect: every
    list-valued field becomes a `numpy` array, other values pass through.
    """
    return {
        key: np.asarray(value) if isinstance(value, list) else value
        for key, value in results.items()
    }


def load_self_test_results(results_path):
    """Load and restore a self-test's raw results JSON file.

    Returns ``None`` (after logging the failure) if `results_path` cannot be
    read or parsed, so a caller such as the results dialog can fall back to
    an empty figure instead of crashing.
    """
    try:
        with open(results_path) as results_file:
            data = json.load(results_file)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Could not load self-test results from {results_path}: {e}")
        return None

    return restore_test_results(data)


class SelfTestResultsSignal(BaseModel):
    """Payload for a single self-test's results (#611).

    The backend writes the raw result dict for `test_name` to a JSON file
    alongside the test's HTML report (see `get_timestamped_results_path`)
    and publishes only its path. Two of the three plotted tests carry 2-D
    capacitance matrices plus scalars, which one self-describing JSON file
    holds more naturally than CSV; keeping the payload itself small also
    avoids pushing raw measurement arrays through the message router. The
    frontend (`dropbot_tools_menu.self_test_dialogs`) reads the file back
    with `load_self_test_results` and renders it interactively via
    `dropbot.self_test.plot_*`.

    Attributes
    ----------
    test_name : str
        Name of the test that ran (e.g. ``"test_voltage"``).
    title : str
        Display title for the results dialog.
    results_path : str
        Absolute path to the JSON file holding the test's raw results.
    failed_channels : list[int], optional
        Channels that failed the test. Only populated for ``test_channels``;
        ``None`` for every other test.
    """

    test_name: StrictStr
    title: StrictStr
    results_path: StrictStr
    failed_channels: Optional[list[StrictInt]] = None


class SelfTestResultsPublisher(ValidatedTopicPublisher):
    """Validated publisher for the ``SELF_TESTS_RESULTS`` topic."""

    validator_class = SelfTestResultsSignal

    def publish(self, test_name, title, results_path, failed_channels=None, **kwargs):
        logger.info(f"SelfTestResultsPublisher: {test_name} -> {results_path}")
        super().publish(
            {
                "test_name": test_name,
                "title": title,
                "results_path": results_path,
                "failed_channels": (
                    [int(channel) for channel in failed_channels]
                    if failed_channels is not None
                    else None
                ),
            },
            **kwargs,
        )

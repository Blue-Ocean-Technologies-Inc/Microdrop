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


class SelfTestResultsSignal(BaseModel):
    """Payload for a single self-test's results (#611).

    The backend renders the result plot to a PNG on disk and hands the
    frontend the file path — never the `matplotlib.Figure` itself — so the
    payload stays JSON-serialisable and the backend stays Qt-free.

    Attributes
    ----------
    test_name : str
        Name of the test that ran (e.g. ``"test_voltage"``).
    title : str
        Display title for the results dialog.
    plot_image_path : str
        Absolute path to the rendered plot image (PNG) on disk.
    failed_channels : list[int], optional
        Channels that failed the test. Only populated for ``test_channels``;
        ``None`` for every other test.
    """

    test_name: StrictStr
    title: StrictStr
    plot_image_path: StrictStr
    failed_channels: Optional[list[StrictInt]] = None


class SelfTestResultsPublisher(ValidatedTopicPublisher):
    """Validated publisher for the ``SELF_TESTS_RESULTS`` topic."""

    validator_class = SelfTestResultsSignal

    def publish(
        self, test_name, title, plot_image_path, failed_channels=None, **kwargs
    ):
        logger.info(f"SelfTestResultsPublisher: {test_name} -> {plot_image_path}")
        super().publish(
            {
                "test_name": test_name,
                "title": title,
                "plot_image_path": plot_image_path,
                "failed_channels": (
                    [int(channel) for channel in failed_channels]
                    if failed_channels is not None
                    else None
                ),
            },
            **kwargs,
        )

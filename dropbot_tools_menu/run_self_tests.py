# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Starting the DropBot self tests from the frontend: the one path the Tools
menu's entries and the self-test reminder's "Run self test" both take."""

# Standard library imports.
from types import SimpleNamespace

# Microdrop package imports.
from dropbot_controller.consts import TEST_ON_BOARD_FEEDBACK_CALIBRATION, TEST_VOLTAGE

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.status_bar_utils import set_status_bar_message

# Local imports.
from .self_test_dialogs import (
    DropbotDisconnectedDialogAction,
    ShowSelfTestIntroDialogAction,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Tests that run without the test board, so do not ask for it first.
_NO_TEST_BOARD_TESTS = (TEST_VOLTAGE, TEST_ON_BOARD_FEEDBACK_CALIBRATION)


def run_self_tests(plugin, task, topic, report_directory):
    """Request the self tests ``topic`` names (a ``dropbot/requests/...``
    test topic), their report written in ``report_directory``. Without a
    DropBot it says so instead; for tests that need the test board it asks
    for the board first, and runs nothing if the user cancels.

    Parameters
    ----------
    plugin
        The DropbotToolsMenuPlugin: whether a DropBot is connected.
    task
        The task whose window parents the dialogs and shows the status.
    """
    window = task.window

    # The dialogs take the parent from an action event's task.
    event = SimpleNamespace(task=task)

    if not plugin.dropbot_connected:
        set_status_bar_message(
            "Warning: Cannot start test, Dropbot is disconnected", window
        )
        DropbotDisconnectedDialogAction().perform(event)

        return

    logger.info("Requesting running self tests for dropbot")

    if topic in _NO_TEST_BOARD_TESTS:
        set_status_bar_message("Running self tests...", window, 30000)

    else:
        set_status_bar_message("Click OK to continue", window)

        if not ShowSelfTestIntroDialogAction().perform(event):
            return

        set_status_bar_message("Running self tests...", window, 15000)

    publish_message(topic=topic, message=report_directory)

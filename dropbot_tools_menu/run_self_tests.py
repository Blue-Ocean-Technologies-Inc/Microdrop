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
from device_viewer.consts import DROPBOT_MAINTENANCE_CATEGORY_ID
from dropbot_controller.consts import TEST_ON_BOARD_FEEDBACK_CALIBRATION, TEST_VOLTAGE
from notifications.consts import SEVERITY_WARNING, notification_publisher

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from .consts import PKG
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
    DropBot it says so instead, in a dialog and a warning notification; for
    tests that need the test board it asks for the board first, and runs
    nothing if the user cancels.

    Parameters
    ----------
    plugin
        The DropbotToolsMenuPlugin: whether a DropBot is connected.
    task
        The task whose window parents the dialogs.
    """
    # The dialogs take the parent from an action event's task.
    event = SimpleNamespace(task=task)

    if not plugin.dropbot_connected:
        # Listed quietly: the dialog below is the interruption.
        notification_publisher.publish(
            {
                "title": "Cannot start self test: DropBot is disconnected",
                "severity": SEVERITY_WARNING,
                "category": "hardware",
                "source": PKG,
                "category_id": DROPBOT_MAINTENANCE_CATEGORY_ID,
                "pop_up": False,
            }
        )
        DropbotDisconnectedDialogAction().perform(event)

        return

    logger.info("Requesting running self tests for dropbot")

    if topic not in _NO_TEST_BOARD_TESTS:
        if not ShowSelfTestIntroDialogAction().perform(event):
            return

    publish_message(topic=topic, message=report_directory)

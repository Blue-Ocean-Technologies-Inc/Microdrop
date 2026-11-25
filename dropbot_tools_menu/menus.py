# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Third-party imports.
from dropbot.hardware_test import ALL_TESTS

# Enthought library imports.
from pyface.tasks.action.api import SMenu
from traits.api import Any, Directory, Int, Property

# Microdrop package imports.
from dropbot_controller.consts import (
    REBOOT,
    RUN_ALL_TESTS,
    START_DEVICE_MONITORING,
    TEST_CHANNELS,
    TEST_ON_BOARD_FEEDBACK_CALIBRATION,
    TEST_SHORTS,
    TEST_VOLTAGE,
)
from microdrop_application.dialogs.pyface_wrapper import OK, warning

# Microdrop utils imports.
from microdrop_utils.dramatiq_traits_helpers import DramatiqMessagePublishAction

# Local imports.
from .run_self_tests import run_self_tests

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class RunTests(DramatiqMessagePublishAction):
    num_tests = Int(1, desc="number of tests run")
    message = Property(Directory, observe="object.application.user_data")
    plugin = Any()

    def _get_message(self, event=None):
        if self.object and hasattr(self.object, "application"):
            return self.object.application.user_data

        return None

    def perform(self, event=None):
        run_self_tests(self.plugin, event.task, self.topic, self.message)


class DropbotRebootAction(DramatiqMessagePublishAction):
    name = "&Reboot Dropbot"
    topic = REBOOT

    def pre_perform(self):
        logger.info("Request user confirmation to reboot Dropbot")

        user_choice = warning(
            None,
            "Rebooting the <b>DropBot</b> will <b>Disconnect</b> the "
            "microcontroller and the DropBot may become <b>Unresponsive</b>. "
            "Do you still want to proceed?",
            title="Dropbot Reboot Warning",
        )

        return user_choice == OK


def dropbot_tools_menu_factory(plugin=None):
    """The Tools > Dropbot menu: the self tests (all, or one at a time), a
    new search for the DropBot, and a reboot."""
    test_actions = [
        RunTests(name="Test &high voltage", topic=TEST_VOLTAGE, plugin=plugin),
        RunTests(
            name="On-board &feedback calibration",
            topic=TEST_ON_BOARD_FEEDBACK_CALIBRATION,
            plugin=plugin,
        ),
        RunTests(name="&Detect shorted channels", topic=TEST_SHORTS, plugin=plugin),
        RunTests(name="Scan &test board", topic=TEST_CHANNELS, plugin=plugin),
    ]
    test_options_menu = SMenu(
        items=test_actions,
        id="dropbot_on_board_self_tests",
        name="&On-board self-tests",
    )
    run_all_tests = RunTests(
        name="&Run all on-board self-tests",
        topic=RUN_ALL_TESTS,
        num_tests=len(ALL_TESTS),
        plugin=plugin,
    )
    dropbot_search = DramatiqMessagePublishAction(
        name="&Search for Dropbot Connection", topic=START_DEVICE_MONITORING
    )

    return SMenu(
        items=[run_all_tests, test_options_menu, dropbot_search, DropbotRebootAction()],
        id="dropbot_tools",
        name="Drop&bot",
    )

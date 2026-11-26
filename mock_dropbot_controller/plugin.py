# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from envisage.plugin import Plugin
from traits.api import List

# Microdrop package imports.
from dropbot_controller.consts import (
    PROTOCOL_FREQUENCY_RANGE_KEY,
    PROTOCOL_VOLTAGE_RANGE_KEY,
)
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from .consts import ACTOR_TOPIC_DICT, CHIP_INSERTED, DROPBOT_CONNECTED, PKG, PKG_name

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class MockDropbotControllerPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def start(self):
        from .mock_controller import (
            MOCK_FREQUENCY_RANGE,
            MOCK_VOLTAGE_RANGE,
            MockDropbotController,
        )

        self.mock_controller = MockDropbotController()
        self.mock_controller.connected = True

        # Overwrite, never seed: app_globals outlives the session, so a
        # previous device's range would otherwise bound the protocol columns.
        app_globals = get_microdrop_redis_globals_manager()
        app_globals[PROTOCOL_VOLTAGE_RANGE_KEY] = list(MOCK_VOLTAGE_RANGE)
        app_globals[PROTOCOL_FREQUENCY_RANGE_KEY] = list(MOCK_FREQUENCY_RANGE)

        # Publish connected signal so the UI picks it up
        publish_message(topic=DROPBOT_CONNECTED, message="mock_dropbot")
        publish_message(topic=CHIP_INSERTED, message="True")
        self.mock_controller.chip_inserted = True

        logger.info(
            "MockDropbotControllerPlugin started — mock device connected with chip"
        )

    def stop(self):
        if hasattr(self, "mock_controller"):
            self.mock_controller.cleanup()
            logger.info("MockDropbotControllerPlugin stopped")

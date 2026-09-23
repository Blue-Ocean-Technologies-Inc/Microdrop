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
from pyface.action.api import Action

# Microdrop package imports.
from microdrop_application.consts import ADVANCED_MODE_CHANGE, ADVANCED_MODE_KEY
from microdrop_application.helpers import (
    get_microdrop_redis_globals_manager,
    is_advanced_mode,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


class AdvancedModeAction(Action):
    id = "advanced_mode_action"
    name = "&Advanced Mode"
    style = "toggle"
    checked = is_advanced_mode()

    def perform(self, event):
        app_globals[ADVANCED_MODE_KEY] = self.checked

        logger.critical(
            "Microdrop Running in Advanced Mode!"
            if self.checked
            else "Microdrop Advanced Mode is Off."
        )

        publish_message(
            topic=ADVANCED_MODE_CHANGE,
            message=str(self.checked),
        )

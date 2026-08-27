# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# This module's package.
import os
from dropbot_controller.consts import REALTIME_MODE_UPDATED, DROPBOT_DISCONNECTED, DROPBOT_CONNECTED
from dropbot_preferences_ui.consts import VOLTAGE_FREQUENCY_RANGE_CHANGED

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        REALTIME_MODE_UPDATED,
        DROPBOT_DISCONNECTED,
        DROPBOT_CONNECTED,
        VOLTAGE_FREQUENCY_RANGE_CHANGED,
    ]
}
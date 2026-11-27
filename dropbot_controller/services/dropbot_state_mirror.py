# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The DropBot backend's connection, chip and power state in app_globals,
announced by ``DROPBOT_STATE_UPDATED`` after every write."""

# Third-party imports.
from redis.exceptions import ConnectionError as RedisConnectionError

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Local imports.
from ..consts import (
    DROPBOT_CHIP_INSERTED_KEY,
    DROPBOT_CONNECTION_STATE_KEY,
    DROPBOT_NO_POWER_KEY,
    DROPBOT_STATE_KEYS,
    dropbot_state_updated_publisher,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


def mirror_dropbot_state(updates):
    """Write ``updates`` (state key -> value) to app_globals, then publish the
    whole state: written first, so a reader the topic wakes sees it."""
    for key, value in updates.items():
        app_globals[key] = value

    dropbot_state_updated_publisher.publish(
        {
            "connected": app_globals.get(DROPBOT_CONNECTION_STATE_KEY, False),
            "chip_inserted": app_globals.get(DROPBOT_CHIP_INSERTED_KEY),
            "no_power": app_globals.get(DROPBOT_NO_POWER_KEY, False),
        }
    )


def clear_dropbot_state():
    """Delete the state keys on a clean stop. A stopped Redis took them
    with it, so its connection error is only logged."""
    try:
        for key in DROPBOT_STATE_KEYS:
            if key in app_globals:
                del app_globals[key]

    except RedisConnectionError as error:
        logger.debug(f"Redis is gone; no DropBot state left to clear: {error}")

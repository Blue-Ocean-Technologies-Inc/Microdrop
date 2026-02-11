# This module's package.
import os
from dropbot_controller.consts import (
    REALTIME_MODE_UPDATED,
    DROPBOT_DISCONNECTED,
    DROPBOT_CONNECTED,
    CHIP_INSERTED,
    CHIP_LOCK_FAILED,
)
from portable_dropbot_controller.consts import PORT_DROPBOT_STATUS_UPDATE

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        REALTIME_MODE_UPDATED,
        DROPBOT_DISCONNECTED,
        DROPBOT_CONNECTED,
        CHIP_INSERTED,
        CHIP_LOCK_FAILED,
        PORT_DROPBOT_STATUS_UPDATE,
    ]
}

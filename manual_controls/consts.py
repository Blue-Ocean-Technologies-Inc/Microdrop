# This module's package.
import os
from dropbot_controller.consts import REALTIME_MODE_UPDATED, DROPBOT_DISCONNECTED, DROPBOT_CONNECTED

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        REALTIME_MODE_UPDATED,
        DROPBOT_DISCONNECTED,
        DROPBOT_CONNECTED
    ]
}
# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

from dropbot_controller.consts import DROPBOT_CONNECTED, DROPBOT_DISCONNECTED

listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        DROPBOT_CONNECTED,
        DROPBOT_DISCONNECTED,
    ]
}

# This module's package.
from dropbot_controller.consts import DROPBOT_CONNECTED, DROPBOT_DISCONNECTED
from portable_dropbot_controller.consts import PORT_DROPBOT_STATUS_UPDATE

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")
listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        DROPBOT_CONNECTED,
        DROPBOT_DISCONNECTED,
        PORT_DROPBOT_STATUS_UPDATE,
    ]
}

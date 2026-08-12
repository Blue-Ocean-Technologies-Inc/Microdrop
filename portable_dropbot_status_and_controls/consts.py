import os

from device_viewer.consts import PROTOCOL_GRID_DISPLAY_STATE, PROTOCOL_RUNNING
from portable_dropbot_controller.consts import (
    MOTORS_UPDATED,
    PORTABLE_DROPBOT_CONNECTED,
    PORTABLE_DROPBOT_DISCONNECTED,
)

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))
#: Placeholder device photo (a DropBot image) until the portable
#: instrument has its own.
PORTABLE_DROPBOT_IMAGE = os.path.join(current_folder_path, "images",
                                      "portable_dropbot.png")

#: The motors pane's listener, separate from the status pane's so the
#: two panes mount and unmount independently.
MOTORS_LISTENER = f"{PKG}_motors_listener"

# Topics the actors declared by this plugin subscribe to.
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "portable_dropbot/signals/#",
        "hardware/signals/#",
        PROTOCOL_RUNNING,
        PROTOCOL_GRID_DISPLAY_STATE,
    ],
    MOTORS_LISTENER: [
        MOTORS_UPDATED,
        PORTABLE_DROPBOT_CONNECTED,
        PORTABLE_DROPBOT_DISCONNECTED,
    ],
}

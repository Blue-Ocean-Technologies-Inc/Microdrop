import os

from dropbot_controller.consts import (
    DROPBOT_CONNECTED,
    DROPBOT_DISCONNECTED,
    CHIP_INSERTED,
    TRAY_TOGGLE_FAILED,
)
from peripheral_controller.consts import ZSTAGE_POSITION_UPDATED
from portable_dropbot_controller.consts import PORT_DROPBOT_STATUS_UPDATE
from protocol_grid.consts import PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

current_folder_path = os.path.dirname(os.path.abspath(__file__))
DROPBOT_IMAGE = os.path.join(current_folder_path, "images", "dropbot.png")
DROPBOT_CHIP_INSERTED_IMAGE = os.path.join(
    current_folder_path, "images", "dropbot-chip-inserted.png"
)

NUM_CAPACITANCE_READINGS_AVERAGED = 5

# Topics actor declared by plugin subscribes to.
ACTOR_TOPIC_DICT = {
    listener_name: [
        PORT_DROPBOT_STATUS_UPDATE,
        "portable_dropbot/signals/#",
        "hardware/signals/#",
        PROTOCOL_RUNNING,
        PROTOCOL_GRID_DISPLAY_STATE,
        DROPBOT_CONNECTED,
        DROPBOT_DISCONNECTED,
        CHIP_INSERTED,
        TRAY_TOGGLE_FAILED,
        ZSTAGE_POSITION_UPDATED,
    ]
}

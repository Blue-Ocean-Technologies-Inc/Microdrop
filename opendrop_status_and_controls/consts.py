import os

from protocol_grid.consts import PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))
OPENDROP_IMAGE = os.path.join(current_folder_path, "images", "opendrop.png")

# User requested one image for both states.
OPENDROP_CONNECTED_IMAGE = OPENDROP_IMAGE
OPENDROP_DISCONNECTED_IMAGE = OPENDROP_IMAGE

# Topics actor declared by plugin subscribes to.
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "opendrop/signals/#",
        "hardware/signals/#",
        PROTOCOL_RUNNING,
        PROTOCOL_GRID_DISPLAY_STATE
    ]
}

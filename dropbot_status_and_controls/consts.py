import os

from dropbot_controller.consts import REALTIME_MODE_UPDATED, DROPBOT_DISCONNECTED, DROPBOT_CONNECTED
from microdrop_style.colors import SUCCESS_COLOR, WARNING_COLOR, GREY

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

# Single listener subscribing to all dropbot signals + calibration data
ACTOR_TOPIC_DICT = {
    listener_name: ["dropbot/signals/#", "ui/calibration_data"]
}

# Image paths
current_folder_path = os.path.dirname(os.path.abspath(__file__))
DROPBOT_IMAGE = os.path.join(current_folder_path, "images", "dropbot.png")
DROPBOT_CHIP_INSERTED_IMAGE = os.path.join(current_folder_path, "images", "dropbot-chip-inserted.png")

NUM_CAPACITANCE_READINGS_AVERAGED = 5

# Status colors
disconnected_color = GREY["lighter"]
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR
BORDER_RADIUS = 4

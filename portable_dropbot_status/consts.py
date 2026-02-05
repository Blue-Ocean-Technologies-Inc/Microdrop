import os

from dropbot_controller.consts import DROPBOT_CONNECTED
from portable_dropbot_controller.consts import PORT_DROPBOT_STATUS_UPDATE

# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))
DROPBOT_IMAGE = os.path.join(current_folder_path, "images", "dropbot.png")
DROPBOT_CHIP_INSERTED_IMAGE = os.path.join(current_folder_path, "images", 'dropbot-chip-inserted.png')

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [PORT_DROPBOT_STATUS_UPDATE, "ui/calibration_data", DROPBOT_CONNECTED]}

NUM_CAPACITANCE_READINGS_AVERAGED = 5

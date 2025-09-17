import os
# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))
DROPBOT_IMAGE = os.path.join(current_folder_path, "images", "dropbot.png")
DROPBOT_CHIP_INSERTED_IMAGE = os.path.join(current_folder_path, "images", 'dropbot-chip-inserted.png')

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": ["dropbot/signals/#", "ui/calibration_data"]}

NUM_CAPACITANCE_READINGS_AVERAGED = 5
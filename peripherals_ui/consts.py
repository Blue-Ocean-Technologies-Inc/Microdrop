import os

from dropbot_controller.consts import SET_REALTIME_MODE

# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ").replace("Ui", "UI")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

from peripheral_controller.consts import DEVICE_NAME

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [f"{DEVICE_NAME}/signals/#", SET_REALTIME_MODE]
}
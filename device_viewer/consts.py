import os
from dropbot_controller.consts import DROPBOT_SETUP_SUCCESS

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

DEFAULT_SVG_FILE = os.path.join(os.path.dirname(__file__), "2x3device.svg")

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
                                 DROPBOT_SETUP_SUCCESS,
    ]}
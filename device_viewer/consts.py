import os
from dropbot_controller.consts import CHIP_INSERTED
from protocol_grid.consts import PROTOCOL_GRID_DISPLAY_STATE

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

DEFAULT_SVG_FILE = os.path.join(os.path.dirname(__file__), "2x3device.svg")

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
                                 CHIP_INSERTED,
                                 PROTOCOL_GRID_DISPLAY_STATE
    ]}
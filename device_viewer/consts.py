import os
from dropbot_controller.consts import CHIP_INSERTED, CAPACITANCE_UPDATED
from protocol_grid.consts import PROTOCOL_GRID_DISPLAY_STATE, DEVICE_VIEWER_STATE_CHANGED, DEVICE_VIEWER_SCREEN_CAPTURE, DEVICE_VIEWER_CAMERA_ACTIVE, DEVICE_VIEWER_SCREEN_RECORDING

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

DEFAULT_SVG_FILE = os.path.join(os.path.dirname(__file__), "90_pin_array.svg")

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        CHIP_INSERTED,
        PROTOCOL_GRID_DISPLAY_STATE,
        DEVICE_VIEWER_STATE_CHANGED,
        CAPACITANCE_UPDATED,
        DEVICE_VIEWER_SCREEN_CAPTURE,
        DEVICE_VIEWER_CAMERA_ACTIVE,
        DEVICE_VIEWER_SCREEN_RECORDING
    ]}

# GUI configuration
DEVICE_VIEWER_SIDEBAR_WIDTH = 270
ALPHA_VIEW_MIN_HEIGHT = 180
LAYERS_VIEW_MIN_HEIGHT = 250
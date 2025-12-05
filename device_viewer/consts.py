import os
from pathlib import Path

from traits.etsconfig.api import ETSConfig

from dropbot_controller.consts import CHIP_INSERTED, CAPACITANCE_UPDATED, DROPLETS_DETECTED
from protocol_grid.consts import PROTOCOL_GRID_DISPLAY_STATE, DEVICE_VIEWER_STATE_CHANGED, DEVICE_VIEWER_SCREEN_CAPTURE, DEVICE_VIEWER_CAMERA_ACTIVE, DEVICE_VIEWER_SCREEN_RECORDING

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        CHIP_INSERTED,
        PROTOCOL_GRID_DISPLAY_STATE,
        DEVICE_VIEWER_STATE_CHANGED,
        CAPACITANCE_UPDATED,
        DEVICE_VIEWER_SCREEN_CAPTURE,
        DEVICE_VIEWER_CAMERA_ACTIVE,
        DEVICE_VIEWER_SCREEN_RECORDING,
        DROPLETS_DETECTED
    ]}

# GUI configuration
DEVICE_VIEWER_SIDEBAR_WIDTH = 270
ALPHA_VIEW_MIN_HEIGHT = 180
LAYERS_VIEW_MIN_HEIGHT = 250

## zoom scaling values:
x_zoom_scale = 1.15
y_zoom_scale = 1.15

## device view margin when auto fit
AUTO_FIT_MARGIN_SCALE = 0.95

# main view config
MASTER_SVG_FILE = Path(__file__).parent / "resources" / "devices" / "90_pin_array.svg"
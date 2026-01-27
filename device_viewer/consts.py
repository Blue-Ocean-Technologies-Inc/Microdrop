import os
from pathlib import Path

from traits.etsconfig.api import ETSConfig

from dropbot_controller.consts import CHIP_INSERTED, CAPACITANCE_UPDATED, DROPLETS_DETECTED
from protocol_grid.consts import PROTOCOL_GRID_DISPLAY_STATE, DEVICE_VIEWER_STATE_CHANGED, DEVICE_VIEWER_SCREEN_CAPTURE, DEVICE_VIEWER_CAMERA_ACTIVE, DEVICE_VIEWER_SCREEN_RECORDING

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

device_modified_tag = " (modified)"

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

# published topics
MEDIA_CAPTURED = "microdrop/device_viewer/camera/media_captured"

# GUI configuration
DEVICE_VIEWER_SIDEBAR_WIDTH = 270
ALPHA_VIEW_MIN_HEIGHT = 180
LAYERS_VIEW_MIN_HEIGHT = 250

## device vew zoom sensitivity
ZOOM_SENSITIVITY = 5

## device view margin when auto fit
AUTO_FIT_MARGIN_SCALE = 95

# main view config
MASTER_SVG_FILE = Path(__file__).parent / "resources" / "devices" / "90_pin_array.svg"

# statusbar messages
camera_place_status_message_text = "Select 4 points on image"
camera_edit_status_message_text = "Drag vertices to align with device outline"
from pathlib import Path

from dropbot_controller.consts import (
    CHIP_INSERTED,
    CAPACITANCE_UPDATED,
    DISABLED_CHANNELS_CHANGED,
    DROPLETS_DETECTED,
    REALTIME_MODE_UPDATED,
    DROPBOT_DISCONNECTED,
    DROPBOT_CONNECTED,
    SHORTS_DETECTED, HALTED,
)
# Device-viewer topics — canonical home (re-exported by protocol_grid.consts for back-compat).
DEVICE_VIEWER_STATE_CHANGED    = "ui/device_viewer/state_changed"
DEVICE_VIEWER_SCREEN_CAPTURE   = "ui/device_viewer/screen_capture"
DEVICE_VIEWER_SCREEN_RECORDING = "ui/device_viewer/screen_recording"
DEVICE_VIEWER_CAMERA_ACTIVE    = "ui/device_viewer/camera_active"
DEVICE_VIEWER_MEDIA_CAPTURED   = "ui/device_viewer/camera/media_captured"

# Shared topics used by device_viewer actor subscriptions (defined here to avoid circular imports
# with protocol_grid.consts, which re-exports the device_viewer topics above).
PROTOCOL_GRID_DISPLAY_STATE    = "ui/protocol_grid/display_state"
PROTOCOL_RUNNING               = "microdrop/protocol_running"

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

device_modified_tag = " (modified)"

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        CHIP_INSERTED,
        REALTIME_MODE_UPDATED,
        PROTOCOL_GRID_DISPLAY_STATE,
        CAPACITANCE_UPDATED,
        DEVICE_VIEWER_SCREEN_CAPTURE,
        DEVICE_VIEWER_CAMERA_ACTIVE,
        DEVICE_VIEWER_SCREEN_RECORDING,
        DROPLETS_DETECTED,
        PROTOCOL_RUNNING,
        DROPBOT_DISCONNECTED,
        DROPBOT_CONNECTED,
        DISABLED_CHANNELS_CHANGED,
        HALTED
    ]
}

# GUI configuration
DEVICE_VIEWER_SIDEBAR_WIDTH = 320
ALPHA_VIEW_MIN_HEIGHT = 180
LAYERS_VIEW_MIN_HEIGHT = 250

# Default electrode channel count; configurable in Device Viewer preferences.
NUMBER_OF_CHANNELS = 120

## device vew zoom sensitivity
ZOOM_SENSITIVITY = 5

## device view margin when auto fit
AUTO_FIT_MARGIN_SCALE = 95

# main view config
MASTER_SVG_FILE = Path(__file__).parent / "resources" / "devices" / "90_pin_array.svg"

# statusbar messages
camera_place_status_message_text = "Select 4 points on image"
camera_edit_status_message_text = "Drag vertices to align with device outline"
import os

from dropbot_controller.consts import (
    DROPBOT_DISCONNECTED,
    CHIP_INSERTED,
    DROPBOT_CONNECTED,
    DROPLETS_DETECTED,
    CAPACITANCE_UPDATED,
)

from peripheral_controller.consts import ZSTAGE_POSITION_UPDATED


# # This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

LISTENER_NAME = f"{PKG}_listener"
DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"
PROTOCOL_GRID_DISPLAY_STATE = "ui/protocol_grid/display_state"
CALIBRATION_DATA = "ui/calibration_data"
DEVICE_VIEWER_SCREEN_CAPTURE = "ui/device_viewer/screen_capture"
DEVICE_VIEWER_SCREEN_RECORDING = "ui/device_viewer/screen_recording"
DEVICE_VIEWER_CAMERA_ACTIVE = "ui/device_viewer/camera_active"

START_PROTOCOL_RUN = "microdrop/protocol_runner/start_protocol_run"


ACTOR_TOPIC_DICT = {
    LISTENER_NAME: [

        START_PROTOCOL_RUN
        # DEVICE_VIEWER_STATE_CHANGED,
        # DROPBOT_DISCONNECTED,
        # CHIP_INSERTED,
        # DROPBOT_CONNECTED,
        # DROPLETS_DETECTED,
        # CALIBRATION_DATA,
        # CAPACITANCE_UPDATED,
        # ZSTAGE_POSITION_UPDATED,
        # # DEVICE_NAME_CHANGED,  #TODO: uncomment when implemented
    ]
}
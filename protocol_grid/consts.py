import os

from PySide6.QtCore import Qt

from dropbot_controller.consts import (DROPBOT_DISCONNECTED, CHIP_INSERTED,
                                       DROPBOT_CONNECTED, DROPLETS_DETECTED,
                                       CAPACITANCE_UPDATED)
from microdrop_style.colors import (
    PRIMARY_SHADE, SECONDARY_SHADE, GREY, BLACK, WHITE
)
from microdrop_style.button_styles import (
    get_button_style, get_button_dimensions, BUTTON_SPACING
)
from peripheral_controller.consts import ZSTAGE_POSITION_UPDATED

ICON_FONT_FAMILY = "Material Symbols Outlined"

# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

PROTOCOL_GRID_LISTENER_NAME = f"{PKG}_listener"

DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"
PROTOCOL_GRID_DISPLAY_STATE = "ui/protocol_grid/display_state"
CALIBRATION_DATA = "ui/calibration_data"
DEVICE_VIEWER_SCREEN_CAPTURE = "ui/device_viewer/screen_capture"
DEVICE_VIEWER_SCREEN_RECORDING = "ui/device_viewer/screen_recording"
DEVICE_VIEWER_CAMERA_ACTIVE = "ui/device_viewer/camera_active"

ACTOR_TOPIC_DICT = {
    PROTOCOL_GRID_LISTENER_NAME: [
        DEVICE_VIEWER_STATE_CHANGED,
        DROPBOT_DISCONNECTED,
        CHIP_INSERTED,
        DROPBOT_CONNECTED,
        DROPLETS_DETECTED,
        CALIBRATION_DATA,
        CAPACITANCE_UPDATED,
        ZSTAGE_POSITION_UPDATED
        # DEVICE_NAME_CHANGED,  #TODO: uncomment when implemented
    ]
}

GROUP_TYPE = "group"
STEP_TYPE = "step"
ROW_TYPE_ROLE = Qt.UserRole + 1

protocol_grid_fields = [
    "Description", "ID", "Repetitions", 
    "Duration", "Voltage", "Force", "Frequency", 
    "Message", "Repeat Duration",
    "Trail Length", "Trail Overlay",
    "Video", "Capture", "Record",
    "Volume Threshold", "Magnet", "Magnet Height (mm)",
    "Max. Path Length", "Run Time"
]
protocol_grid_column_widths = [
    120, 70, 80, 70, 70, 70, 90, 80, 130, 100, 100, 50, 140, 70, 110, 140, 90
]
hidden_fields = ["UID"]
all_fields = protocol_grid_fields + hidden_fields
fixed_fields = {"Description", "ID"}
field_groupings = [
            (None, [f for f in protocol_grid_fields if f not in [
                "Repeat Duration", "Repetitions", 
                "Trail Length", "Video", "Capture", "Record", "Volume Threshold", 
                "Magnet", "Magnet Height (mm)", "Trail Overlay"
            ] and f not in fixed_fields]),
            ("Device Viewer:", ["Repeat Duration", "Repetitions", "Trail Length", 
                                "Trail Overlay", "Video", "Capture", "Record"]),
            ("Dropbot:", ["Volume Threshold"]),
            ("Magnet:", ["Magnet", "Magnet Height (mm)"]),
        ]
step_defaults = {
    "Description": "Step",
    "ID": "", 
    "Repetitions": "1",
    "Duration": "1.0",
    "Voltage": "100.0",
    "Force": "",
    "Frequency": "10000",
    "Message": "",
    "Repeat Duration": "0.0",
    "Trail Length": "1",
    "Trail Overlay": "0",
    "Video": "1",
    "Capture": "1",
    "Record": "1",
    "Volume Threshold": "0.00",
    "Magnet": "0",
    "Magnet Height (mm)": "Default",
    "Max. Path Length": "0",
    "Run Time": "0.0",
    "UID": ""
}
group_defaults = {
    "Description": "Group",
    "ID": "",
    "Repetitions": "1",
    "Duration": "1.0",
    "Voltage": "",
    "Frequency": "",
    "Trail Length": "",
    "Run Time": "",
}

copy_fields_for_new_step = [
    "Repetitions",
    "Duration",
    "Voltage",
    "Force",
    "Frequency",
    "Message",
    "Repeat Duration",
    "Trail Length",
    "Trail Overlay",
    "Video",
    "Capture",
    "Record",
    "Volume Threshold",
    "Magnet",
    "Magnet Height (mm)",
    "Max. Path Length",
    "Run Time"
]

# Button styling constants (now imported from button_styles)
BUTTON_MIN_WIDTH, BUTTON_MIN_HEIGHT = get_button_dimensions("default")
BUTTON_BORDER_RADIUS = 4

# Get button styles based on theme
def get_light_mode_stylesheet():
    """Get light mode stylesheet with button styles."""
    from microdrop_style.button_styles import get_complete_stylesheet
    return get_complete_stylesheet("light", "default")

def get_dark_mode_stylesheet():
    """Get dark mode stylesheet with button styles."""
    from microdrop_style.button_styles import get_complete_stylesheet
    return get_complete_stylesheet("dark", "default")

# Legacy constants for backward compatibility
LIGHT_MODE_STYLESHEET = get_light_mode_stylesheet()
DARK_MODE_STYLESHEET = get_dark_mode_stylesheet()

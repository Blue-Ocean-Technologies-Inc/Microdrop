import os

from PySide6.QtCore import Qt

from dropbot_controller.consts import (DROPBOT_DISCONNECTED, CHIP_INSERTED,
                                       DROPBOT_CONNECTED, DROPLETS_DETECTED,
                                       CAPACITANCE_UPDATED)
from dropbot_preferences_ui.models import VoltageFrequencyRangePreferences
from dropbot_preferences_ui.consts import VOLTAGE_FREQUENCY_RANGE_CHANGED
from microdrop_application.consts import ADVANCED_MODE_CHANGE

from microdrop_style.button_styles import get_button_dimensions
from peripheral_controller.consts import ZSTAGE_POSITION_UPDATED

ICON_FONT_FAMILY = "Material Symbols Outlined"

# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

PROTOCOL_GRID_LISTENER_NAME = f"{PKG}_listener"

# Re-exported from device_viewer.consts for back-compat (canonical home moved there).
# Safe to remove this re-export block once PPT-9 deletes the protocol_grid plugin.
from device_viewer.consts import (
    DEVICE_VIEWER_SCREEN_CAPTURE,
    DEVICE_VIEWER_SCREEN_RECORDING,
    DEVICE_VIEWER_CAMERA_ACTIVE,
    DEVICE_VIEWER_MEDIA_CAPTURED,
    CALIBRATION_DATA,
)

DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"
STEP_PARAMS_COMMIT = "ui/device_viewer/step_params_commit"
PROTOCOL_GRID_DISPLAY_STATE = "ui/protocol_grid/display_state"
PROTOCOL_RUNNING = "microdrop/protocol_running"
ROUTES_EXECUTING = "ui/device_viewer/routes_executing"
DEVICE_VIEWER_RECORDING_STATE = "ui/device_viewer/recording_state"

ACTOR_TOPIC_DICT = {
    PROTOCOL_GRID_LISTENER_NAME: [
        DEVICE_VIEWER_STATE_CHANGED,
        STEP_PARAMS_COMMIT,
        DROPBOT_DISCONNECTED,
        CHIP_INSERTED,
        DROPBOT_CONNECTED,
        DROPLETS_DETECTED,
        CALIBRATION_DATA,
        CAPACITANCE_UPDATED,
        ZSTAGE_POSITION_UPDATED,
        DEVICE_VIEWER_MEDIA_CAPTURED,
        ADVANCED_MODE_CHANGE,
        DEVICE_VIEWER_RECORDING_STATE,
        ROUTES_EXECUTING,
        VOLTAGE_FREQUENCY_RANGE_CHANGED,
    ]
}

GROUP_TYPE = "group"
STEP_TYPE = "step"
ROW_TYPE_ROLE = Qt.UserRole + 1
REPEAT_DURATION_CONTROLS_ROLE = Qt.UserRole + 3

protocol_grid_fields = [
    "Description", "ID", "Repetitions",
    "Duration", "Voltage", "Force", "Frequency",
    "Message", "Repeat Duration",
    "Trail Length", "Trail Overlay",
    "Ramp Up", "Ramp Dn", "Lin Reps",
    "Video", "Capture", "Record",
    "Volume Threshold", "Magnet", "Magnet Height (mm)",
    "Max. Path Length", "Run Time"
]
protocol_grid_column_widths = [
    120, 70, 80, 70, 70, 70, 90, 80, 130, 100, 100, 80, 80, 80, 50, 140, 70, 110, 140, 90
]
hidden_fields = ["UID"]
all_fields = protocol_grid_fields + hidden_fields
fixed_fields = {"Description", "ID"}
field_groupings = [
            (None, [f for f in protocol_grid_fields if f not in [
                "Repeat Duration", "Repetitions",
                "Trail Length", "Video", "Capture", "Record", "Volume Threshold",
                "Magnet", "Magnet Height (mm)", "Trail Overlay",
                "Ramp Up", "Ramp Dn", "Lin Reps"
            ] and f not in fixed_fields]),
            ("Device Viewer:", ["Repeat Duration", "Repetitions", "Trail Length",
                                "Trail Overlay", "Ramp Up", "Ramp Dn", "Lin Reps",
                                "Video", "Capture", "Record"]),
            ("Dropbot:", ["Volume Threshold"]),
            ("Magnet:", ["Magnet", "Magnet Height (mm)"]),
        ]
step_defaults = {
    "Description": "Step",
    "ID": "",
    "Repetitions": "1",
    "Duration": "1.0",
    "Force": "",
    "Voltage": f"{float(VoltageFrequencyRangePreferences().ui_default_voltage)}",
    "Frequency": f"{float(VoltageFrequencyRangePreferences().ui_default_frequency)}",
    "Message": "",
    "Repeat Duration": "0",
    "Trail Length": "1",
    "Trail Overlay": "0",
    "Ramp Up": "0",
    "Ramp Dn": "0",
    "Lin Reps": "0",
    "Video": "0",
    "Capture": "0",
    "Record": "0",
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
    "Ramp Up",
    "Ramp Dn",
    "Lin Reps",
    "Video",
    "Capture",
    "Record",
    "Volume Threshold",
    "Magnet",
    "Magnet Height (mm)",
    "Max. Path Length",
    "Run Time"
]

CHECKBOX_COLS = ("Video", "Capture", "Record", "Magnet", "Ramp Up", "Ramp Dn", "Lin Reps")

ALLOWED_group_fields = {
    "Description",
    "ID",
    "Repetitions",
    "Run Time",
}

# Button styling constants (now imported from button_styles)
BUTTON_MIN_WIDTH, BUTTON_MIN_HEIGHT = get_button_dimensions("default")
BUTTON_BORDER_RADIUS = 4

DEFAULT_CAMERA_PREWARM_SECONDS = 3.0
DEFAULT_REALTIME_SETTLING_SECONDS = 1.0
DEFAULT_LOGS_SETTLING_SECONDS = 3.0

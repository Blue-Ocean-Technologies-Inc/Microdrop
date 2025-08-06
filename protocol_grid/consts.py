import os

from PySide6.QtCore import Qt

from dropbot_controller.consts import (DROPBOT_DISCONNECTED, CHIP_INSERTED,
                                       DROPBOT_CONNECTED, DROPLETS_DETECTED)
from microdrop_style.colors import(PRIMARY_SHADE, SECONDARY_SHADE, WHITE,
                                   WHITE, BLACK, GREY)

ICON_FONT_FAMILY = "Material Symbols Outlined"

# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

PROTOCOL_GRID_LISTENER_NAME = f"{PKG}_listener"

DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"
PROTOCOL_GRID_DISPLAY_STATE = "ui/protocol_grid/display_state"
CALIBRATION_DATA = "ui/calibration_data"
DEVICE_NAME_CHANGED = "ui/device_viewer/device_name_changed"

ACTOR_TOPIC_DICT = {
    PROTOCOL_GRID_LISTENER_NAME: [
        DEVICE_VIEWER_STATE_CHANGED,
        DROPBOT_DISCONNECTED,
        CHIP_INSERTED,
        DROPBOT_CONNECTED,
        DROPLETS_DETECTED,
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
    "Trail Length", "Trail Overlay", "Video", 
    "Volume Threshold", "Magnet", "Magnet Height",
    "Max. Path Length", "Run Time"
]
protocol_grid_column_widths = [
    120, 70, 70, 70, 70, 70, 80, 70, 110, 80, 90, 50, 120, 60, 100, 120, 90
]
hidden_fields = ["UID"]
all_fields = protocol_grid_fields + hidden_fields
fixed_fields = {"Description", "ID"}
field_groupings = [
            (None, [f for f in protocol_grid_fields if f not in [
                "Repeat Duration", "Repetitions", 
                "Trail Length", "Video", "Volume Threshold", 
                "Magnet", "Magnet Height", "Trail Overlay"
            ] and f not in fixed_fields]),
            ("Device Viewer:", ["Repeat Duration", "Repetitions", "Trail Length", 
                                "Trail Overlay", "Video"]),
            ("Dropbot:", ["Volume Threshold"]),
            ("Magnet:", ["Magnet", "Magnet Height"]),
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
    "Volume Threshold": "0.00",
    "Magnet": "0",
    "Magnet Height": "0",    
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

DARK_MODE_STYLESHEET = f"""
            QPushButton {{ 
                font-family: {ICON_FONT_FAMILY}; 
                font-size: 22px; 
                padding: 4px 8px 4px 8px;
                background-color: {WHITE};
                color: {BLACK};
            }} 
            QPushButton:hover {{ 
                color: {SECONDARY_SHADE[700]}; 
                background-color: {GREY['light']};
            }}
            QPushButton:pressed {{
                background-color: {GREY['dark']};
            }}
            QPushButton:disabled {{
                color: {WHITE};
                background-color: {GREY['light']};
            }}
            QToolTip {{
                background-color: {BLACK};
                color: {WHITE};
                padding: 4px 8px 4px 8px;
                font-size: 12pt;
                border-radius: 4px;
            }}
        """

LIGHT_MODE_STYLESHEET = f"""
            QPushButton {{ 
                font-family: {ICON_FONT_FAMILY}; 
                font-size: 22px; 
                padding: 4px 8px 4px 8px;
                background-color: {BLACK};
                color: {WHITE};
            }} 
            QPushButton:hover {{ 
                color: {SECONDARY_SHADE[700]}; 
                background-color: {GREY['light']};
            }}
            QPushButton:pressed {{
                background-color: {GREY['dark']};
            }}
            QPushButton:disabled {{
                color: {WHITE};
                background-color: {GREY['light']};
            }}
            QToolTip {{
                background-color: {WHITE};
                color: {BLACK};
                padding: 4px 8px 4px 8px;
                font-size: 12pt;
                border-radius: 4px;
            }}
        """
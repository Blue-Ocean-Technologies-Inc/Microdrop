import os

from PySide6.QtCore import Qt

# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"

ACTOR_TOPIC_DICT = {
    "protocol_grid_listener": [
        DEVICE_VIEWER_STATE_CHANGED,
    ]
}

GROUP_TYPE = "group"
STEP_TYPE = "step"
ROW_TYPE_ROLE = Qt.UserRole + 1

protocol_grid_fields = [
    "Description", "ID", "Repetitions", 
    "Duration", "Voltage", "Frequency", 
    "Message", "Repeat Duration",
    "Trail Length", "Trail Overlay", "Video", 
    "Volume Threshold", "Magnet", "Magnet Height",
    "Max. Path Length", "Run Time"
]
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
    "Run Time": "0.0"
}
group_defaults = {
    "Description": "Group",
    "ID": "",
    "Repetitions": "1",
    "Duration": "1.0",
    "Voltage": "",
    "Frequency": "",
    "Message": "",
    "Repeat Duration": "",
    "Trail Length": "",
    "Trail Overlay": "",
    "Video": "",
    "Volume Threshold": "",
    "Magnet": "",
    "Magnet Height": "",   
    "Max. Path Length": "",
    "Run Time": "" 
}
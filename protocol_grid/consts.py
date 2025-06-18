import os

from PySide6.QtCore import Qt

# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

GROUP_TYPE = "group"
STEP_TYPE = "step"
ROW_TYPE_ROLE = Qt.UserRole + 1

protocol_grid_fields = ["Description", "ID", "Repetitions", 
                        "Duration", "Voltage", "Frequency", 
                        "Label", "Message", "Repeat Duration",
                        "Trail Length", "Video", "Volume Threshold" 
                    ]
fixed_fields = {"Description", "ID"}
field_groupings = [
            (None, [f for f in protocol_grid_fields if f not in [
                "Label", "Message", "Repeat Duration", "Repetitions", "Trail Length", "Video", "Volume Threshold"
            ] and f not in fixed_fields]),

            ("step_label_plugin:", ["Label"]),
            ("user_prompt_plugin:", ["Message"]),
            ("droplet_planning_plugin:", ["Repeat Duration", "Repetitions", "Trail Length"]),
            ("dmf_device_ui_plugin:", ["Video"]),
            ("dropbot_plugin:", ["Volume Threshold"])
        ]

step_defaults = {
    "Description": "Step",
    "ID": "", 
    "Repetitions": "1",
    "Duration": "1.00",
    "Voltage": "100.00",
    "Frequency": "10000.00",
    "Label": "",
    "Message": "",
    "Repeat Duration": "0",
    "Trail Length": "1",
    "Video": "1",
    "Volume Threshold": "0.0",
}

group_defaults = {
    "Description": "Group",
    "ID": "",
    "Repetitions": "1",
    "Duration": "",
    "Voltage": "",
    "Frequency": "",
    "Label": "",
    "Message": "",
    "Repeat Duration": "",
    "Trail Length": "",
    "Video": "",
    "Volume Threshold": "",
}
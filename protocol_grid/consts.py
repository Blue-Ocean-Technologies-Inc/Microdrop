import os
# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

protocol_grid_fields = ["Description", "ID", "Repetitions", 
                        "Duration", "Voltage", "Frequency", 
                        "Message", "Repeat Duration",
                        "Trail Length", "Video", "Volume Threshold" 
                    ]

#TODO add utility function(s) in widget.py to make new step/group
#using these defaults
step_defaults = {
    "Description": "Step",
    "ID": "", 
    "Repetitions": "1",
    "Duration": "1.00",
    "Voltage": "0.00",
    "Frequency": "0.00",
    "Message": "",
    "Repeat Duration": "",
    "Trail Length": "",
    "Video": "",
    "Volume Threshold": "",
}

group_defaults = {
    "Description": "Group",
    "ID": "",
    "Repetitions": "1",
    "Duration": "",
    "Voltage": "",
    "Frequency": "",
    "Message": "",
    "Repeat Duration": "",
    "Trail Length": "",
    "Video": "",
    "Volume Threshold": "",
}
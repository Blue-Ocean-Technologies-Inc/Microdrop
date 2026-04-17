import os

from dropbot_preferences_ui.consts import VOLTAGE_FREQUENCY_RANGE_CHANGED
from microdrop_style.colors import ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, GREY
from protocol_grid.consts import PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

# Single listener subscribing to all dropbot signals + calibration data
ACTOR_TOPIC_DICT = {
    listener_name: ["dropbot/signals/#", "hardware/signals/#", "ui/calibration_data", PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE, VOLTAGE_FREQUENCY_RANGE_CHANGED]
}

# Image paths
current_folder_path = os.path.dirname(os.path.abspath(__file__))
DROPBOT_IMAGE = os.path.join(current_folder_path, "images", "dropbot.png")
DROPBOT_CHIP_INSERTED_IMAGE = os.path.join(current_folder_path, "images", "dropbot-chip-inserted.png")

NUM_CAPACITANCE_READINGS_AVERAGED = 5

# Dielectric materials and their relative permittivity values.
# Used to calculate dielectric thickness from device capacitance via:
#   d = epsilon * epsilon_0 / C_device
DIELECTRIC_MATERIALS = {
    "Pick a dielectric...": float('nan'),
    "Parylene C": 3.1,
    "CYTOP": 2.1,
    "Teflon AF": 1.93,
    "SiO2": 3.9,
    "SU-8": 3.2,
    "Parylene N": 2.65,
    "Parylene D": 2.84,
    "PDMS": 2.7,
    "Si3N4": 7.5,
}

# Status colors
disconnected_color = GREY["lighter"]
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR
halted_color = ERROR_COLOR
BORDER_RADIUS = 4

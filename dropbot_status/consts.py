import os
# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))
DROPBOT_IMAGE = os.path.join(current_folder_path, "images", "dropbot.png")
DROPBOT_CHIP_INSERTED_IMAGE = os.path.join(current_folder_path, "images", 'dropbot-chip-inserted.png')

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": ["dropbot/signals/#", "ui/calibration_data"]}

NUM_CAPACITANCE_READINGS_AVERAGED = 5

# Dielectric materials and their relative permittivity values.
# Used to calculate dielectric thickness from device capacitance via:
#   d = epsilon * epsilon_0 / C_device
DIELECTRIC_MATERIALS = {
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

# Permittivity of free space in F/m
EPSILON_0 = 8.854e-12
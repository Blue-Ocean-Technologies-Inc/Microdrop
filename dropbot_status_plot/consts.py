import os
from dropbot_controller.consts import CAPACITANCE_UPDATED
# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

VOLTAGE_LISTENER = f"{PKG}_voltage_listener"
CAPACITANCE_LISTENER = f"{PKG}_capacitance_listener"
VOLTAGE_CAPACITANCE_LISTENER = f"{PKG}_voltage_capacitance_listener"

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    VOLTAGE_LISTENER: [CAPACITANCE_UPDATED],
    CAPACITANCE_LISTENER: [CAPACITANCE_UPDATED],
    VOLTAGE_CAPACITANCE_LISTENER: [CAPACITANCE_UPDATED],
}
# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")


PORT_DROPBOT_STATUS_UPDATE = "portable_dropbot/signals/board_status_update"
TOGGLE_DROPBOT_LOADING = "dropbot/requests/toggle_tray"
# Define topics for new controls
SET_CHIP_LOCK = "dropbot/requests/lock_chip"
SET_LIGHT_INTENSITY = "dropbot/requests/set_light_intensity"

SET_MOTOR_RELATIVE_MOVE = "dropbot/requests/motor_relative_move"
SET_MOTOR_ABSOLUTE_MOVE = "dropbot/requests/motor_absolute_move"
SET_MOTOR_HOME = "dropbot/requests/motor_home"
SET_TOGGLE_MOTOR = "dropbot/requests/toggle_motor"

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "dropbot/requests/#",
    ]}
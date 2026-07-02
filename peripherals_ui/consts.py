import os

from dropbot_controller.consts import SET_REALTIME_MODE

# # This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ").replace("Ui", "UI")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

from microdrop_style.colors import GREY, SUCCESS_COLOR

from peripheral_controller.consts import DEVICE_NAME, START_DEVICE_MONITORING

listener_name = f"{PKG}_listener"

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    listener_name: [f"{DEVICE_NAME}/signals/#", SET_REALTIME_MODE, START_DEVICE_MONITORING]
}

# Status colors. The Z-Stage has no chip/"no device" sub-state, so connected
# maps straight to the green "connected" color (same palette as the other
# device panes, owned locally so the pane doesn't reach into another plugin).
disconnected_color = GREY["lighter"]
connected_color = SUCCESS_COLOR
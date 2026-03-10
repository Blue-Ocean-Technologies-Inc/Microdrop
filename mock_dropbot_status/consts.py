from dropbot_controller.consts import (
    CAPACITANCE_UPDATED, CHIP_INSERTED, SHORTS_DETECTED,
    HALTED, DROPBOT_CONNECTED, DROPBOT_DISCONNECTED,
    REALTIME_MODE_UPDATED, DROPLETS_DETECTED,
)
from protocol_grid.consts import PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        "dropbot/signals/#",
        "hardware/signals/#",
        PROTOCOL_RUNNING,
        PROTOCOL_GRID_DISPLAY_STATE,
    ]
}

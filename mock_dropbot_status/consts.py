from dropbot_controller.consts import (
    CAPACITANCE_UPDATED, CHIP_INSERTED, SHORTS_DETECTED,
    HALTED, DROPBOT_CONNECTED, DROPBOT_DISCONNECTED,
    REALTIME_MODE_UPDATED, DROPLETS_DETECTED,
)
from mock_dropbot_controller.consts import (
    MOCK_SIMULATE_CONNECT, MOCK_SIMULATE_DISCONNECT,
    MOCK_CHANGE_SIM_SETTINGS, MOCK_SIMULATE_CHIP_INSERT,
    MOCK_SIMULATE_SHORTS, MOCK_SIMULATE_HALT,
    MOCK_ACTUATED_CHANNELS_UPDATED, MOCK_STREAM_STATUS_UPDATED,
)
from protocol_grid.consts import PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

listener_name = f"{PKG}_listener"

ACTOR_TOPIC_DICT = {
    listener_name: [
        "dropbot/signals/#",
        "hardware/signals/#",
        "mock_dropbot/signals/#",
        PROTOCOL_RUNNING,
        PROTOCOL_GRID_DISPLAY_STATE,
    ]
}

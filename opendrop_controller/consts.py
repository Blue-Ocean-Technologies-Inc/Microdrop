# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# OpenDrop protocol constants (from OpenDropController4_25.pde)
DEFAULT_BAUD_RATE = 115200
DEFAULT_SERIAL_TIMEOUT = 0.05
DEFAULT_READ_TIMEOUT_MS = 500
NUM_ELECTRODE_BYTES = 18
NUM_ELECTRODES = 144
NUM_CONTROL_OUT_BYTES = 14
NUM_CONTROL_IN_BYTES = 24
MIN_TEMPERATURE_C = 20
MAX_TEMPERATURE_C = 120
DEFAULT_TEMPERATURE_C = 25
DEFAULT_FEEDBACK_ENABLED = False

# OpenDrop hardware ID (Feather M0): use VID:PID to discover port
OPENDROP_VID_PID = "239A:800B"

# OpenDrop Topics published by this plugin
OPENDROP_CONNECTED = "opendrop/signals/connected"
OPENDROP_DISCONNECTED = "opendrop/signals/disconnected"
OPENDROP_TEMPERATURES_UPDATED = "opendrop/signals/temperatures_updated"
OPENDROP_FEEDBACK_UPDATED = "opendrop/signals/feedback_updated"
OPENDROP_BOARD_INFO = "opendrop/signals/board_info"
REALTIME_MODE_UPDATED = "opendrop/signals/realtime_mode_updated"

# OpenDrop request topics
START_DEVICE_MONITORING = "opendrop/requests/start_device_monitoring"
RETRY_CONNECTION = "opendrop/requests/retry_connection"
ELECTRODES_STATE_CHANGE = "opendrop/requests/electrodes_state_change"
SET_REALTIME_MODE = "opendrop/requests/set_realtime_mode"
SET_FEEDBACK = "opendrop/requests/set_feedback"
SET_TEMPERATURES = "opendrop/requests/set_temperatures"
SET_TEMPERATURE_1 = "opendrop/requests/set_temperature_1"
SET_TEMPERATURE_2 = "opendrop/requests/set_temperature_2"
SET_TEMPERATURE_3 = "opendrop/requests/set_temperature_3"
CHANGE_SETTINGS = "opendrop/requests/change_settings"

# Compatibility topics to allow existing DropBot-oriented UIs/routes to work with OpenDrop.
DROPBOT_CONNECTED = "dropbot/signals/connected"
DROPBOT_DISCONNECTED = "dropbot/signals/disconnected"
DROPBOT_REALTIME_MODE_UPDATED = "dropbot/signals/realtime_mode_updated"
DROPBOT_ELECTRODES_STATE_CHANGE = "dropbot/requests/electrodes_state_change"
DROPBOT_SET_REALTIME_MODE = "dropbot/requests/set_realtime_mode"
DROPBOT_START_DEVICE_MONITORING = "dropbot/requests/start_device_monitoring"
DROPBOT_RETRY_CONNECTION = "dropbot/requests/retry_connection"

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "opendrop/requests/#",
        "dropbot/requests/#",
        OPENDROP_CONNECTED,
        OPENDROP_DISCONNECTED,
        DROPBOT_CONNECTED,
        DROPBOT_DISCONNECTED,
    ]
}
# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topics published by this plugin
NO_OPENDROP_AVAILABLE = 'dropbot/signals/warnings/no_dropbot_available'
CHIP_INSERTED = 'dropbot/signals/chip_inserted'
OPENDROP_CONNECTED = 'dropbot/signals/connected'
OPENDROP_DISCONNECTED = 'dropbot/signals/disconnected'
DROPLETS_DETECTED = 'dropbot/signals/drops_detected'

# Dropbot Services Topics -- Offered by default from the dropbot monitor mixin in this package
START_DEVICE_MONITORING = "dropbot/requests/start_device_monitoring"
RETRY_CONNECTION = "dropbot/requests/retry_connection"
SET_VOLTAGE = "dropbot/requests/set_voltage"
SET_FREQUENCY = "dropbot/requests/set_frequency"
SET_REALTIME_MODE = "dropbot/requests/set_realtime_mode"
ELECTRODES_STATE_CHANGE = 'dropbot/requests/electrodes_state_change'

import json

class TestEvent:
    SESSION_START = "SESSION_START"
    PROGRESS = "PROGRESS"
    SESSION_END = "SESSION_END"
    ERROR = "ERROR"

def create_test_progress_message(event_type, **kwargs):
    """Helper to ensure consistent message structure"""
    return json.dumps({"type": event_type, "payload": kwargs})


# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "dropbot/requests/#",
        OPENDROP_CONNECTED,
        OPENDROP_DISCONNECTED,
    ]}

DEFAULT_VOLTAGE = 200
DEFAULT_FREQUENCY = 10_000

# This module's package.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# dropbot DB3-120 hardware id
DROPBOT_DB3_120_HWID = 'VID:PID=16C0:0483'

# Chip may have been inserted before connecting, so `chip-inserted`
# event may have been missed.
# Explicitly check if chip is inserted by reading **active low**
# `OUTPUT_ENABLE_PIN`.
OUTPUT_ENABLE_PIN = 22


# Topics published by this plugin
NO_DROPBOT_AVAILABLE = 'dropbot/signals/warnings/no_dropbot_available'
NO_POWER = 'dropbot/signals/warnings/no_power'
HALTED = 'dropbot/signals/halted'
CHIP_INSERTED = 'dropbot/signals/chip_inserted'
SHORTS_DETECTED = 'dropbot/signals/shorts_detected'
CAPACITANCE_UPDATED = 'dropbot/signals/capacitance_updated'
SELF_TESTS_PROGRESS = 'dropbot/signals/self_tests_progress'
REALTIME_MODE_UPDATED = 'hardware/signals/realtime_mode_updated'
DROPBOT_CONNECTED = 'hardware/signals/connected'
DROPBOT_DISCONNECTED = 'hardware/signals/disconnected'
DROPLETS_DETECTED = 'dropbot/signals/drops_detected'
DISABLED_CHANNELS_CHANGED = 'hardware/signals/disabled_channels_changed'

# Dropbot Services Topics -- Offered by default from the dropbot monitor mixin in this package
START_DEVICE_MONITORING = "dropbot/requests/start_device_monitoring"
DETECT_SHORTS = "dropbot/requests/detect_shorts"
RETRY_CONNECTION = "dropbot/requests/retry_connection"
HALT = "dropbot/requests/halt"
SET_VOLTAGE = "dropbot/requests/set_voltage"
SET_FREQUENCY = "dropbot/requests/set_frequency"
SET_REALTIME_MODE = "hardware/requests/set_realtime_mode"
RUN_ALL_TESTS = "dropbot/requests/run_all_tests"
TEST_VOLTAGE = "dropbot/requests/test_voltage"
TEST_ON_BOARD_FEEDBACK_CALIBRATION = "dropbot/requests/test_on_board_feedback_calibration"
TEST_SHORTS = "dropbot/requests/test_shorts"
TEST_CHANNELS = "dropbot/requests/test_channels"
CHIP_CHECK = "dropbot/requests/chip_check"
SELF_TEST_CANCEL = "dropbot/requests/self_test_cancel"
DETECT_DROPLETS = "dropbot/requests/detect_droplets"
CHANGE_SETTINGS = "dropbot/requests/change_settings"

import json

class TestEvent:
    SESSION_START = "SESSION_START"
    PROGRESS = "PROGRESS"
    SESSION_END = "SESSION_END"
    ERROR = "ERROR"

def create_test_progress_message(event_type, **kwargs):
    """Helper to ensure consistent message structure"""
    return json.dumps({"type": event_type, "payload": kwargs})

# Dropbot Error Topics
DROPBOT_ERROR = 'dropbot/error'

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "dropbot/requests/#",
        "hardware/requests/#",
        DROPBOT_CONNECTED,
        DROPBOT_DISCONNECTED,
        SELF_TEST_CANCEL
    ]}

# Constants for droplet detection
# capacitance threshold to detect droplets. This is the multiplier to the minimum device capacitance
DROPLET_DETECTION_CAPACITANCE_THRESHOLD = 10
DROPLET_DETECTION_FREQUENCY = 1000  # 1 kHz for droplet detection

DEFAULT_VOLTAGE = 100
DEFAULT_FREQUENCY = 10_000

# Frontend-configurable range limits for voltage and frequency
DEFAULT_MIN_VOLTAGE = 30
DEFAULT_MAX_VOLTAGE = 150
DEFAULT_MIN_FREQUENCY = 100
DEFAULT_MAX_FREQUENCY = 20_000

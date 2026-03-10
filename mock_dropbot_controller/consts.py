from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Re-export all topic constants from the real dropbot controller
from dropbot_controller.consts import (
    NO_DROPBOT_AVAILABLE, NO_POWER, HALTED, CHIP_INSERTED,
    SHORTS_DETECTED, CAPACITANCE_UPDATED, SELF_TESTS_PROGRESS,
    REALTIME_MODE_UPDATED, DROPBOT_CONNECTED, DROPBOT_DISCONNECTED,
    DROPLETS_DETECTED, START_DEVICE_MONITORING, DETECT_SHORTS,
    RETRY_CONNECTION, HALT, SET_VOLTAGE, SET_FREQUENCY,
    SET_REALTIME_MODE, RUN_ALL_TESTS, TEST_VOLTAGE,
    TEST_ON_BOARD_FEEDBACK_CALIBRATION, TEST_SHORTS, TEST_CHANNELS,
    CHIP_CHECK, SELF_TEST_CANCEL, DETECT_DROPLETS, CHANGE_SETTINGS,
    DEFAULT_VOLTAGE, DEFAULT_FREQUENCY, TestEvent,
    create_test_progress_message,
)

from electrode_controller.consts import ELECTRODES_STATE_CHANGE

# Topics this mock actor subscribes to (same as real dropbot)
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "dropbot/requests/#",
        "hardware/requests/#",
        DROPBOT_CONNECTED,
        DROPBOT_DISCONNECTED,
        SELF_TEST_CANCEL,
    ]
}

# Mock-specific defaults
DEFAULT_BASE_CAPACITANCE_PF = 3.0
DEFAULT_CAPACITANCE_DELTA_PF = 1.5
DEFAULT_CAPACITANCE_NOISE_PF = 0.2
DEFAULT_STREAM_INTERVAL_MS = 200
DEFAULT_NUM_CHANNELS = 120

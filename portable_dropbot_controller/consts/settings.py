# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Portable DropBot Settings preferences node and the app_globals
keys this plugin owns."""

#: The ETS preferences node both the backend's PortableDropbotPreferences and
#: the frontend's settings pane bind to, so the frontend never imports the
#: backend class (same shape as VOLTAGE_FREQUENCY_RANGE_PREFERENCES_PATH).
PORTABLE_DROPBOT_PREFERENCES_PATH = "microdrop.portable_dropbot_settings"

# ---------------------------------------------------------------------------
# app_globals keys (stored in APP_GLOBALS_REDIS_HASH via the redis client)
# ---------------------------------------------------------------------------
# Owner-publishes pattern: PortableDropbotPreferences seeds these via
# preferences_name_map (trait name doubles as the hash key), matching
# dropbot_controller/preferences.py and dropbot_preferences_ui's
# VOLTAGE_FREQUENCY_RANGE_APP_GLOBALS_KEYS.
BAUD_RATE_KEY = "baud_rate"
PORT_HINT_KEY = "port_hint"
DEFAULT_VOLTAGE_KEY = "default_voltage"
DEFAULT_FREQUENCY_KEY = "default_frequency"
DEFAULT_LIGHT_INTENSITY_KEY = "default_light_intensity"
FAN_BOARD_KEY = "fan_board"
CHIP_DETECT_RULE_KEY = "chip_detect_rule"
CHIP_ENGAGE_MODE_KEY = "chip_engage_mode"
DROPLET_DETECTION_THRESHOLD_PF_KEY = "droplet_detection_threshold_pf"

PORTABLE_DROPBOT_PREFERENCES_APP_GLOBALS_KEYS = (
    BAUD_RATE_KEY,
    PORT_HINT_KEY,
    DEFAULT_VOLTAGE_KEY,
    DEFAULT_FREQUENCY_KEY,
    DEFAULT_LIGHT_INTENSITY_KEY,
    FAN_BOARD_KEY,
    CHIP_DETECT_RULE_KEY,
    CHIP_ENGAGE_MODE_KEY,
    DROPLET_DETECTION_THRESHOLD_PF_KEY,
)

# Last applied electrodes_state_change request.
LAST_CHANNEL_STATES_REQUESTED_KEY = "last_channel_states_requested"

APP_GLOBALS_KEYS = [
    *PORTABLE_DROPBOT_PREFERENCES_APP_GLOBALS_KEYS,
    LAST_CHANNEL_STATES_REQUESTED_KEY,
]

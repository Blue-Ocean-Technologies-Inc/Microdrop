# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from traits.api import Dict, Enum, Int, Property, Str

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Local imports.
from .consts import (
    BAUD_RATE_KEY,
    CHIP_DETECT_RULE_KEY,
    CHIP_DETECT_RULES,
    DEFAULT_BAUD_RATE,
    DEFAULT_CHIP_DETECT_RULE,
    DEFAULT_FAN_BOARD,
    DEFAULT_FREQUENCY,
    DEFAULT_FREQUENCY_KEY,
    DEFAULT_LIGHT_INTENSITY,
    DEFAULT_LIGHT_INTENSITY_KEY,
    DEFAULT_VOLTAGE,
    DEFAULT_VOLTAGE_KEY,
    FAN_BOARD_KEY,
    FAN_BOARDS,
    PORT_HINT_KEY,
    PORTABLE_DROPBOT_PREFERENCES_APP_GLOBALS_KEYS,
    PORTABLE_DROPBOT_PREFERENCES_PATH,
)

preferences_names = PORTABLE_DROPBOT_PREFERENCES_APP_GLOBALS_KEYS

app_globals = get_microdrop_redis_globals_manager()


class PortableDropbotPreferences(PreferencesHelper):
    preferences_path = PORTABLE_DROPBOT_PREFERENCES_PATH

    baud_rate = Int(
        desc="Starting serial baud rate; the driver probes its own whitelist beyond it."
    )
    port_hint = Str(
        desc="Optional preferred serial port (e.g. COM3), "
        "tried before scanning — the hardware has no "
        "VID:PID identity to discover it by."
    )
    default_voltage = Int(desc="HV amplitude applied on connect (V).")
    default_frequency = Int(desc="HV frequency applied on connect (Hz).")
    default_light_intensity = Int(
        desc="Illumination LED brightness applied on connect (%)."
    )
    fan_board = Enum(
        *FAN_BOARDS,
        desc="Board whose fan the status pane's fan toggle drives "
        "when a set_fan request names none.",
    )
    chip_detect_rule = Enum(
        *CHIP_DETECT_RULES,
        desc="Which chip_on_pad contact masks count as a chip on the pad.",
    )

    preferences_name_map = Property(Dict)

    def _baud_rate_default(self):
        return int(app_globals.get(BAUD_RATE_KEY, DEFAULT_BAUD_RATE))

    def _port_hint_default(self):
        return str(app_globals.get(PORT_HINT_KEY, ""))

    def _default_voltage_default(self):
        return int(app_globals.get(DEFAULT_VOLTAGE_KEY, DEFAULT_VOLTAGE))

    def _default_frequency_default(self):
        return int(app_globals.get(DEFAULT_FREQUENCY_KEY, DEFAULT_FREQUENCY))

    def _default_light_intensity_default(self):
        return int(
            app_globals.get(DEFAULT_LIGHT_INTENSITY_KEY, DEFAULT_LIGHT_INTENSITY)
        )

    def _fan_board_default(self):
        return str(app_globals.get(FAN_BOARD_KEY, DEFAULT_FAN_BOARD))

    def _chip_detect_rule_default(self):
        return str(app_globals.get(CHIP_DETECT_RULE_KEY, DEFAULT_CHIP_DETECT_RULE))

    def _get_preferences_name_map(self):
        return {pref: getattr(self, pref) for pref in preferences_names}

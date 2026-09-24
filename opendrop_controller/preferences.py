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
from traits.api import Bool, Dict, Float, Int, Property, Range, Str

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Local imports.
from .consts import (
    BAUD_RATE_KEY,
    DEFAULT_BAUD_RATE,
    DEFAULT_FEEDBACK_ENABLED,
    DEFAULT_READ_TIMEOUT_MS,
    DEFAULT_SERIAL_TIMEOUT,
    DEFAULT_TEMPERATURE_C,
    FEEDBACK_ENABLED_KEY,
    MAX_TEMPERATURE_C,
    MIN_TEMPERATURE_C,
    OPENDROP_PREFERENCES_APP_GLOBALS_KEYS,
    PORT_HINT_KEY,
    READ_TIMEOUT_MS_KEY,
    SERIAL_TIMEOUT_S_KEY,
    TEMPERATURE_1_KEY,
    TEMPERATURE_2_KEY,
    TEMPERATURE_3_KEY,
)

preferences_names = OPENDROP_PREFERENCES_APP_GLOBALS_KEYS

app_globals = get_microdrop_redis_globals_manager()


class OpenDropPreferences(PreferencesHelper):
    preferences_path = "microdrop.opendrop_settings"

    baud_rate = Int(desc="Serial baud rate for OpenDrop controller.")
    serial_timeout_s = Float(desc="Per-read serial timeout in seconds.")
    read_timeout_ms = Int(desc="State transaction timeout in milliseconds.")
    port_hint = Str(desc="Optional preferred serial port (e.g. /dev/ttyUSB0).")
    feedback_enabled = Bool(desc="Enable OpenDrop feedback bit in control payload.")

    temperature_1 = Range(
        MIN_TEMPERATURE_C,
        MAX_TEMPERATURE_C,
        value=DEFAULT_TEMPERATURE_C,
        desc="Temperature setpoint channel 1 (C).",
    )
    temperature_2 = Range(
        MIN_TEMPERATURE_C,
        MAX_TEMPERATURE_C,
        value=DEFAULT_TEMPERATURE_C,
        desc="Temperature setpoint channel 2 (C).",
    )
    temperature_3 = Range(
        MIN_TEMPERATURE_C,
        MAX_TEMPERATURE_C,
        value=DEFAULT_TEMPERATURE_C,
        desc="Temperature setpoint channel 3 (C).",
    )

    preferences_name_map = Property(Dict)

    def _baud_rate_default(self):
        return int(app_globals.get(BAUD_RATE_KEY, DEFAULT_BAUD_RATE))

    def _serial_timeout_s_default(self):
        return float(app_globals.get(SERIAL_TIMEOUT_S_KEY, DEFAULT_SERIAL_TIMEOUT))

    def _read_timeout_ms_default(self):
        return int(app_globals.get(READ_TIMEOUT_MS_KEY, DEFAULT_READ_TIMEOUT_MS))

    def _port_hint_default(self):
        return str(app_globals.get(PORT_HINT_KEY, ""))

    def _feedback_enabled_default(self):
        return bool(app_globals.get(FEEDBACK_ENABLED_KEY, DEFAULT_FEEDBACK_ENABLED))

    def _temperature_1_default(self):
        return int(app_globals.get(TEMPERATURE_1_KEY, DEFAULT_TEMPERATURE_C))

    def _temperature_2_default(self):
        return int(app_globals.get(TEMPERATURE_2_KEY, DEFAULT_TEMPERATURE_C))

    def _temperature_3_default(self):
        return int(app_globals.get(TEMPERATURE_3_KEY, DEFAULT_TEMPERATURE_C))

    def _get_preferences_name_map(self):
        return {pref: getattr(self, pref) for pref in preferences_names}

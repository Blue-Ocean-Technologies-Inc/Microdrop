from apptools.preferences.api import PreferencesHelper
from traits.api import Bool, Dict, Float, Int, Property, Range, Str

from microdrop_application.helpers import get_microdrop_redis_globals_manager

from .consts import (
    DEFAULT_BAUD_RATE,
    DEFAULT_FEEDBACK_ENABLED,
    DEFAULT_READ_TIMEOUT_MS,
    DEFAULT_SERIAL_TIMEOUT,
    DEFAULT_TEMPERATURE_C,
    MAX_TEMPERATURE_C,
    MIN_TEMPERATURE_C,
)

preferences_names = [
    "baud_rate",
    "serial_timeout_s",
    "read_timeout_ms",
    "port_hint",
    "feedback_enabled",
    "temperature_1",
    "temperature_2",
    "temperature_3",
]

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
        return int(app_globals.get("baud_rate", DEFAULT_BAUD_RATE))

    def _serial_timeout_s_default(self):
        return float(app_globals.get("serial_timeout_s", DEFAULT_SERIAL_TIMEOUT))

    def _read_timeout_ms_default(self):
        return int(app_globals.get("read_timeout_ms", DEFAULT_READ_TIMEOUT_MS))

    def _port_hint_default(self):
        return str(app_globals.get("port_hint", ""))

    def _feedback_enabled_default(self):
        return bool(app_globals.get("feedback_enabled", DEFAULT_FEEDBACK_ENABLED))

    def _temperature_1_default(self):
        return int(app_globals.get("temperature_1", DEFAULT_TEMPERATURE_C))

    def _temperature_2_default(self):
        return int(app_globals.get("temperature_2", DEFAULT_TEMPERATURE_C))

    def _temperature_3_default(self):
        return int(app_globals.get("temperature_3", DEFAULT_TEMPERATURE_C))

    def _get_preferences_name_map(self):
        return {pref: getattr(self, pref) for pref in preferences_names}

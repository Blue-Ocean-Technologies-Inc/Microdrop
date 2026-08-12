from apptools.preferences.api import PreferencesHelper
from traits.api import Dict, Int, Property, Str

from microdrop_application.helpers import get_microdrop_redis_globals_manager

from .consts import DEFAULT_BAUD_RATE, DEFAULT_FREQUENCY, DEFAULT_VOLTAGE

preferences_names = [
    "baud_rate",
    "port_hint",
    "default_voltage",
    "default_frequency",
]

app_globals = get_microdrop_redis_globals_manager()


class PortableDropbotPreferences(PreferencesHelper):
    preferences_path = "microdrop.portable_dropbot_settings"

    baud_rate = Int(desc="Starting serial baud rate; the driver probes "
                         "its own whitelist beyond it.")
    port_hint = Str(desc="Optional preferred serial port (e.g. COM3), "
                         "tried before scanning — the hardware has no "
                         "VID:PID identity to discover it by.")
    default_voltage = Int(desc="HV amplitude applied on connect (V).")
    default_frequency = Int(desc="HV frequency applied on connect (Hz).")

    preferences_name_map = Property(Dict)

    def _baud_rate_default(self):
        return int(app_globals.get("baud_rate", DEFAULT_BAUD_RATE))

    def _port_hint_default(self):
        return str(app_globals.get("port_hint", ""))

    def _default_voltage_default(self):
        return int(app_globals.get("default_voltage", DEFAULT_VOLTAGE))

    def _default_frequency_default(self):
        return int(app_globals.get("default_frequency",
                                   DEFAULT_FREQUENCY))

    def _get_preferences_name_map(self):
        return {pref: getattr(self, pref) for pref in preferences_names}

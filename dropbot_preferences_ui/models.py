from apptools.preferences.preferences_helper import PreferencesHelper
from traits.trait_types import Range

from dropbot_preferences_ui.consts import UI_DEFAULT_MIN_VOLTAGE, UI_DEFAULT_MAX_VOLTAGE, UI_DEFAULT_MIN_FREQUENCY, \
    UI_DEFAULT_MAX_FREQUENCY


class VoltageFrequencyRangePreferences(PreferencesHelper):
    """Frontend-only preferences for voltage/frequency spinner range limits.

    These control the min/max bounds on voltage and frequency spinners across
    all frontend plugins (manual controls, dropbot status, protocol grid).
    Persisted under a separate preferences path from DropbotPreferences since
    they are purely a UI concern and do not affect backend hardware validation.
    """

    preferences_path = "microdrop.voltage_frequency_range"

    ui_min_voltage = Range(low=0, high=300, value=UI_DEFAULT_MIN_VOLTAGE,
                           desc="minimum allowed voltage in V")
    ui_max_voltage = Range(low=0, high=300, value=UI_DEFAULT_MAX_VOLTAGE,
                           desc="maximum allowed voltage in V")
    ui_min_frequency = Range(low=0, high=100_000, value=UI_DEFAULT_MIN_FREQUENCY,
                             desc="minimum allowed frequency in Hz")
    ui_max_frequency = Range(low=0, high=100_000, value=UI_DEFAULT_MAX_FREQUENCY,
                             desc="maximum allowed frequency in Hz")

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Default range limits for voltage (V) and frequency (Hz) spinners
UI_DEFAULT_MIN_VOLTAGE = 30
UI_DEFAULT_MAX_VOLTAGE = 140
UI_DEFAULT_MIN_FREQUENCY = 100
UI_DEFAULT_MAX_FREQUENCY = 10_000

# Topic published when the user changes voltage/frequency range preferences
VOLTAGE_FREQUENCY_RANGE_CHANGED = "ui/preferences/voltage_frequency_range_changed"
# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Default range limits for voltage (V) and frequency (Hz) spinners
DEFAULT_MIN_VOLTAGE = 30
DEFAULT_MAX_VOLTAGE = 140
DEFAULT_MIN_FREQUENCY = 100
DEFAULT_MAX_FREQUENCY = 20_000

# Topic published when the user changes voltage/frequency range preferences
VOLTAGE_FREQUENCY_RANGE_CHANGED = "ui/preferences/voltage_frequency_range_changed"
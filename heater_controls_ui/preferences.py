"""Heater UI preferences.

A small PreferencesHelper on the SAME "Peripheral Settings" node the Z-Stage
preferences use (``microdrop.peripheral_settings``), holding only the heater's
own trait — so the heater plugin needs no import from the Z-Stage/magnet
plugin, and values saved before the split keep working (same node + key).
"""
from apptools.preferences.api import PreferencesHelper
from traits.api import Bool


class HeaterPreferences(PreferencesHelper):
    """Heater-owned slice of the shared Peripheral Settings node."""

    preferences_path = "microdrop.peripheral_settings"

    # Whether to warn ("will apply when streaming starts") when the user
    # changes a setpoint while streaming is off.
    heater_show_stream_off_warning = Bool(
        True, desc="Show the 'applies when streaming starts' warning when "
                   "setting a heater setpoint while streaming is off"
    )

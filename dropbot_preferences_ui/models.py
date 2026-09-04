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
from apptools.preferences.preferences_helper import PreferencesHelper
from traits.api import Range, observe

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Local imports.
from .consts import (
    UI_DEFAULT_FREQUENCY,
    UI_DEFAULT_MAX_FREQUENCY,
    UI_DEFAULT_MAX_VOLTAGE,
    UI_DEFAULT_MIN_FREQUENCY,
    UI_DEFAULT_MIN_VOLTAGE,
    UI_DEFAULT_VOLTAGE,
    VOLTAGE_FREQUENCY_RANGE_APP_GLOBALS_KEYS,
    VOLTAGE_FREQUENCY_RANGE_PREFERENCES_PATH,
)

app_globals = get_microdrop_redis_globals_manager()


class VoltageFrequencyRangePreferences(PreferencesHelper):
    """Frontend-only preferences for voltage/frequency spinner configuration.

    These control the min/max bounds and default values on voltage and frequency
    spinners across all frontend plugins (manual controls, dropbot status,
    protocol grid). Persisted under a separate preferences path from
    DropbotPreferences since they are purely a UI concern and do not affect
    backend hardware validation.

    Owner-publishes pattern (#610): every trait here mirrors into the Redis
    app_globals hash under its own name, so other frontend plugins can read
    the live range/defaults without importing this class.
    """

    preferences_path = VOLTAGE_FREQUENCY_RANGE_PREFERENCES_PATH

    ui_min_voltage = Range(
        low=0,
        high=300,
        value=UI_DEFAULT_MIN_VOLTAGE,
        desc="minimum allowed voltage in V",
    )
    ui_max_voltage = Range(
        low=0,
        high=300,
        value=UI_DEFAULT_MAX_VOLTAGE,
        desc="maximum allowed voltage in V",
    )
    ui_min_frequency = Range(
        low=0,
        high=100_000,
        value=UI_DEFAULT_MIN_FREQUENCY,
        desc="minimum allowed frequency in Hz",
    )
    ui_max_frequency = Range(
        low=0,
        high=100_000,
        value=UI_DEFAULT_MAX_FREQUENCY,
        desc="maximum allowed frequency in Hz",
    )

    # Last-applied values — persisted so spinners restore to previous session's setting
    ui_default_voltage = Range(
        low="ui_min_voltage",
        high="ui_max_voltage",
        value=UI_DEFAULT_VOLTAGE,
        desc="default voltage for UI spinners in V",
    )
    ui_default_frequency = Range(
        low="ui_min_frequency",
        high="ui_max_frequency",
        value=UI_DEFAULT_FREQUENCY,
        desc="default frequency for UI spinners in Hz",
    )

    def traits_init(self):
        """Seed app_globals with the persisted values on first use, so a
        reader that beats the preferences pane to construction still sees
        this plugin's real state instead of the trait declarations' defaults."""
        for key in VOLTAGE_FREQUENCY_RANGE_APP_GLOBALS_KEYS:
            if key not in app_globals:
                app_globals[key] = getattr(self, key)

    @observe(
        "ui_min_voltage, ui_max_voltage, ui_default_voltage, "
        "ui_min_frequency, ui_max_frequency, ui_default_frequency"
    )
    def _publish_to_app_globals(self, event):
        """Mirror any change (from the preferences pane, or any other
        frontend plugin's spinner) into app_globals for readers."""
        app_globals[event.name] = event.new

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# Default range limits for voltage (V) and frequency (Hz) spinners
UI_DEFAULT_MIN_VOLTAGE = 30
UI_DEFAULT_MAX_VOLTAGE = 140
UI_DEFAULT_MIN_FREQUENCY = 100
UI_DEFAULT_MAX_FREQUENCY = 10_000

# Default voltage/frequency for UI spinners at startup
UI_DEFAULT_VOLTAGE = 100  # V
UI_DEFAULT_FREQUENCY = 10_000  # Hz

# Topic published when the user changes voltage/frequency range preferences
VOLTAGE_FREQUENCY_RANGE_CHANGED = "ui/preferences/voltage_frequency_range_changed"

# ETS preferences node VoltageFrequencyRangePreferences persists to. Exported
# so other frontend plugins can write to it by path (via apptools'
# default preferences node) without importing the PreferencesHelper class
# itself (#610).
VOLTAGE_FREQUENCY_RANGE_PREFERENCES_PATH = "microdrop.ui.voltage_frequency_range"

# Redis app_globals keys VoltageFrequencyRangePreferences publishes its live
# state under (owner-publishes pattern, #610) — trait name doubles as the
# hash key. Other frontend plugins (e.g. dropbot_status_and_controls) read
# these instead of importing dropbot_preferences_ui.models.
UI_MIN_VOLTAGE_KEY = "ui_min_voltage"
UI_MAX_VOLTAGE_KEY = "ui_max_voltage"
UI_DEFAULT_VOLTAGE_KEY = "ui_default_voltage"
UI_MIN_FREQUENCY_KEY = "ui_min_frequency"
UI_MAX_FREQUENCY_KEY = "ui_max_frequency"
UI_DEFAULT_FREQUENCY_KEY = "ui_default_frequency"

VOLTAGE_FREQUENCY_RANGE_APP_GLOBALS_KEYS = (
    UI_MIN_VOLTAGE_KEY,
    UI_MAX_VOLTAGE_KEY,
    UI_DEFAULT_VOLTAGE_KEY,
    UI_MIN_FREQUENCY_KEY,
    UI_MAX_FREQUENCY_KEY,
    UI_DEFAULT_FREQUENCY_KEY,
)


def __getattr__(name):
    """Expose the preferences helper through the consts contract.

    `VoltageFrequencyRangePreferences` (models.py) is the typed accessor for
    the persisted UI voltage/frequency preferences, so sibling plugins may use
    it under the consts-only import rule. Resolved lazily because models.py
    imports this module.
    """
    if name == "VoltageFrequencyRangePreferences":
        from .models import VoltageFrequencyRangePreferences

        return VoltageFrequencyRangePreferences
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

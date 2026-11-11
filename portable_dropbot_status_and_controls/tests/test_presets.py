# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Preset values parse tolerantly from the Portable DropBot Settings text,
and a running pane's model re-parses when that text changes."""

# Microdrop package imports.
from portable_dropbot_controller.consts import PMT_GAIN_BOUNDS, TEMP_TARGET_C_BOUNDS
from portable_dropbot_status_and_controls.consts import (
    DEFAULT_GAIN_PRESETS,
    DEFAULT_MOVE_PRESETS,
    DEFAULT_TEMPERATURE_PRESETS,
    MOVE_DISTANCE_MM_BOUNDS,
    PRESET_SLOTS_MAX,
)
from portable_dropbot_status_and_controls.models.more_controls_model import (
    PortableDropbotMoreControlsModel,
)
from portable_dropbot_status_and_controls.models.motors_model import (
    PortableDropbotMotorsModel,
)
from portable_dropbot_status_and_controls.models.pmt_capture_model import (
    PortableDropbotPmtCaptureModel,
)
from portable_dropbot_status_and_controls.models.presets import parse_presets
from portable_dropbot_status_and_controls.preferences import (
    PortableDropbotSettingsPreferences,
)


def test_parse_keeps_the_typed_order():
    assert parse_presets("192, 64 128", 0, 255) == [192, 64, 128]


def test_parse_skips_what_is_not_a_number():
    assert parse_presets("10, abc,, nan, inf, 20;, 30", 0, 255) == [10, 30]


def test_parse_clamps_into_bounds_and_rounds():
    assert parse_presets("-5, 300, 12.6", 0, 255) == [0, 255, 13]
    assert parse_presets("37.25, 200", -50.0, 150.0, decimals=1) == [37.2, 150.0]


def test_parse_drops_repeats_after_rounding():
    assert parse_presets("1, 1.0004, 2, 1", -10.0, 10.0, decimals=3) == [1.0, 2.0]


def test_parse_drops_zero_only_when_asked():
    text = "-0.0001, 0, 1"

    assert parse_presets(text, -10.0, 10.0, decimals=3) == [0.0, 1.0]
    assert parse_presets(text, -10.0, 10.0, decimals=3, nonzero=True) == [1.0]


def test_parse_caps_the_slots():
    text = ", ".join(str(n) for n in range(PRESET_SLOTS_MAX + 4))

    assert parse_presets(text, 0, 255) == list(range(PRESET_SLOTS_MAX))


def test_parse_of_empty_text_is_empty():
    assert parse_presets("", 0, 255) == []


def test_preferences_expose_the_default_text():
    preferences = PortableDropbotSettingsPreferences()

    assert preferences.gain_presets == DEFAULT_GAIN_PRESETS
    assert preferences.temperature_presets == DEFAULT_TEMPERATURE_PRESETS
    assert preferences.move_presets == DEFAULT_MOVE_PRESETS


def test_models_default_to_the_parsed_defaults():
    more_controls = PortableDropbotMoreControlsModel()

    assert PortableDropbotMotorsModel().move_presets == parse_presets(
        DEFAULT_MOVE_PRESETS, *MOVE_DISTANCE_MM_BOUNDS, decimals=3, nonzero=True
    )
    assert more_controls.gain_presets == parse_presets(
        DEFAULT_GAIN_PRESETS, *PMT_GAIN_BOUNDS
    )
    assert more_controls.temperature_presets == parse_presets(
        DEFAULT_TEMPERATURE_PRESETS, *TEMP_TARGET_C_BOUNDS, decimals=1
    )
    assert PortableDropbotPmtCaptureModel().gain_presets == more_controls.gain_presets


def test_models_follow_the_preferences():
    preferences = PortableDropbotSettingsPreferences(move_presets="5, 0, -2.5")
    motors = PortableDropbotMotorsModel(preferences=preferences)
    more_controls = PortableDropbotMoreControlsModel(preferences=preferences)
    pmt_capture = PortableDropbotPmtCaptureModel(preferences=preferences)

    assert motors.move_presets == [5.0, -2.5]

    preferences.move_presets = "0.25"
    preferences.gain_presets = "10, 20"
    preferences.temperature_presets = "40.5"

    assert motors.move_presets == [0.25]
    assert more_controls.gain_presets == [10, 20]
    assert pmt_capture.gain_presets == [10, 20]
    assert more_controls.temperature_presets == [40.5]

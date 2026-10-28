# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Rules of the battery model: fill glyph, percent text, levels, staleness."""

# Third-party imports.
import pytest

# Microdrop package imports.
from rpi_battery_status.consts import (
    LEVEL_ABSENT,
    LEVEL_ALERT,
    LEVEL_CRITICAL,
    LEVEL_LOW,
    LEVEL_NORMAL,
    LEVEL_UNAVAILABLE,
    STALE_AFTER_S,
    UNKNOWN_GLYPH,
    UNKNOWN_PERCENT_TEXT,
)
from rpi_battery_status.models.battery_status import BatteryStatus

NOW = 1_800_000_000.0


def fed(**fields):
    """Return a model fed one fresh snapshot carrying ``fields``."""
    model = BatteryStatus()
    model.apply_snapshot({"schema": 1, "timestamp": NOW, **fields}, NOW)

    return model


@pytest.mark.parametrize(
    "soc, glyph",
    [
        (0, "battery_0_bar"),
        (7, "battery_0_bar"),
        (8, "battery_1_bar"),
        (50, "battery_4_bar"),
        (85, "battery_6_bar"),
        (93, "battery_full"),
        (100, "battery_full"),
        (120, "battery_full"),
    ],
)
def test_fill_glyph_tracks_the_percentage(soc, glyph):
    assert fed(soc=soc).glyph == glyph


@pytest.mark.parametrize(
    "soc, glyph",
    [
        (3, "battery_charging_20"),
        (34, "battery_charging_30"),
        (50, "battery_charging_60"),
        (100, "battery_charging_full"),
    ],
)
def test_charging_uses_the_charging_variant(soc, glyph):
    assert fed(soc=soc, charging=True).glyph == glyph


def test_percent_text_is_rounded():
    assert fed(soc=34.48).percent_text == "34 %"


@pytest.mark.parametrize("soc", [None, "73", True])
def test_unknown_percentage_shows_dashes(soc):
    model = fed(soc=soc)

    assert model.percent_text == UNKNOWN_PERCENT_TEXT
    assert model.glyph == UNKNOWN_GLYPH
    assert model.level == LEVEL_NORMAL


def test_a_new_model_is_unavailable():
    model = BatteryStatus()

    assert model.level == LEVEL_UNAVAILABLE
    assert model.percent_text == UNKNOWN_PERCENT_TEXT
    assert model.tooltip == "Battery monitor unavailable"


def test_a_stale_snapshot_is_unavailable():
    model = BatteryStatus()
    model.apply_snapshot({"timestamp": NOW, "soc": 80}, NOW + STALE_AFTER_S)

    assert model.level == LEVEL_UNAVAILABLE
    assert model.glyph == UNKNOWN_GLYPH
    assert model.percent_text == UNKNOWN_PERCENT_TEXT


def test_a_snapshot_without_timestamp_is_unavailable():
    assert fed(timestamp=None, soc=80).level == LEVEL_UNAVAILABLE


def test_mark_unavailable_overrides_the_last_snapshot():
    model = fed(soc=80)
    model.mark_unavailable()

    assert model.level == LEVEL_UNAVAILABLE


def test_absent_battery_hides_the_percentage():
    model = fed(soc=50, battery_absent=True, alert=True)

    assert model.level == LEVEL_ABSENT
    assert model.percent_text == UNKNOWN_PERCENT_TEXT
    assert model.tooltip == "No battery connected"


def test_alert_wins_over_critical():
    assert fed(soc=5, alert=True).level == LEVEL_ALERT


def test_below_critical_percent_is_critical():
    assert fed(soc=14.9).level == LEVEL_CRITICAL
    assert fed(soc=15).level == LEVEL_LOW
    assert fed(soc=39.9).level == LEVEL_LOW
    assert fed(soc=40).level == LEVEL_NORMAL


@pytest.mark.parametrize("unknown", [None, -1])
def test_null_and_minus_one_times_are_unknown(unknown):
    model = fed(soc=50, time_to_empty_s=unknown, time_to_full_s=unknown)

    assert model.time_to_empty is None
    assert model.time_to_full is None


def test_discharging_tooltip_shows_time_to_empty():
    model = fed(soc=73.4, voltage=23.44, current=1.2, time_to_empty_s=3900)

    assert model.tooltip == (
        "Battery 73 % · 23.4 V · 1.2 A · discharging · 1 h 05 min to empty"
    )


def test_real_pi_charging_snapshot(pi_charging_snapshot):
    model = BatteryStatus()
    model.apply_snapshot(pi_charging_snapshot, pi_charging_snapshot["timestamp"] + 1)

    assert model.glyph == "battery_charging_30"
    assert model.percent_text == "34 %"
    assert model.level == LEVEL_LOW
    assert model.tooltip == (
        "Battery 34 % · 23.6 V · 5.9 A · charging · 11 h 03 min to full"
    )

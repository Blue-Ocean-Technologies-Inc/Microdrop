# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Rules of the battery model: glyph, text, levels, staleness, panel rows."""

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


def test_real_pi_charging_snapshot_details(pi_charging_snapshot):
    model = BatteryStatus()
    model.apply_snapshot(pi_charging_snapshot, pi_charging_snapshot["timestamp"] + 1)

    assert model.voltage_per_cell == 3.9375
    assert model.power == pytest.approx(-139.3875)
    assert model.state == "Charging"
    assert model.cells == 6
    assert model.chemistry == "li-ion"
    assert model.soc_source == "coulomb"
    assert model.remaining_ah == pytest.approx(34.484282657375246)

    assert model.headline == ""
    assert model.charge_text == "34 %"
    assert model.voltage_text == "23.6 V (3.94 V/cell)"
    assert model.current_text == "5.9 A into the pack"
    assert model.power_text == "139 W"
    assert model.state_text == "Charging"
    assert model.time_text == "11 h 03 min to full"
    assert model.pack_text == "6 cells · li-ion · 34.5 Ah left"
    assert model.source_text == "coulomb counting"


def test_discharging_details():
    model = fed(
        soc=73.4, current=1.24, power=28.6, state="Discharging", time_to_empty_s=3900
    )

    assert model.current_text == "1.2 A draw"
    assert model.power_text == "29 W"
    assert model.state_text == "Discharging"
    assert model.time_text == "1 h 05 min to empty"


def test_idle_current_has_no_direction():
    assert fed(current=0.02).current_text == "0.0 A"


@pytest.mark.parametrize(
    "soc_source, text",
    [("voltage", "voltage curve"), ("blend", "blend"), ("kalman", "kalman")],
)
def test_source_text_maps_known_sources(soc_source, text):
    assert fed(soc_source=soc_source).source_text == text


def test_voltage_text_without_per_cell():
    assert fed(voltage=23.44).voltage_text == "23.4 V"


def test_pack_text_drops_unknown_parts():
    assert fed(cells=6, remaining_ah=-1).pack_text == "6 cells"
    assert fed(chemistry="li-ion", remaining_ah=12.0).pack_text == (
        "li-ion · 12.0 Ah left"
    )


def test_alert_is_flagged_in_the_state_text():
    assert fed(state="Discharging", alert=True).state_text == (
        "Discharging — low-voltage alert"
    )
    assert fed(alert=True).state_text == "Low-voltage alert"


def test_unknown_details_are_empty():
    model = fed(
        soc=None,
        voltage="23.6",
        voltage_per_cell=None,
        current=None,
        power=True,
        state=7,
        cells=6.0,
        chemistry=None,
        soc_source=None,
        remaining_ah=None,
        time_to_empty_s=-1,
    )

    assert model.headline == ""
    assert model.charge_text == "Unknown"

    for text in (
        model.voltage_text,
        model.current_text,
        model.power_text,
        model.state_text,
        model.time_text,
        model.pack_text,
        model.source_text,
    ):
        assert text == ""


def test_unavailable_and_absent_headlines():
    assert BatteryStatus().headline == "Battery monitor unavailable"
    assert BatteryStatus().charge_text == "Unknown"

    absent = fed(soc=50, battery_absent=True)

    assert absent.headline == "No battery connected"
    assert absent.charge_text == "Unknown"
    assert absent.tooltip == absent.headline

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for force_math helpers (guards + behaviour).

The legacy ForceCalculationService parity tests were dropped in PPT-9 (#371)
when protocol_grid was deleted; force_math is now the sole implementation and
the behavioural cases below pin its outputs directly.

force_for_step's own tests moved to microdrop_utils/tests/test_force_math_helpers.py
in #610, alongside the function itself — it is pure math shared by more than
one plugin. What remains here is specific to this plugin's app-globals-backed
calibration lookup."""

from dropbot_protocol_controls.services import force_math
from dropbot_protocol_controls.services.force_math import (
    current_full_electrode_capacitance_per_unit_area,
    full_electrode_capacitance_per_unit_area,
)


class _FakeGlobals:
    """In-memory stand-in for the Redis app-globals proxy so the
    current_capacitance_per_unit_area tests stay deterministic and don't
    need a running Redis server."""

    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


def test_capacitance_per_unit_area_none_liquid_returns_none():
    assert full_electrode_capacitance_per_unit_area(None, 0.5) is None


def test_capacitance_per_unit_area_none_filler_returns_none():
    assert full_electrode_capacitance_per_unit_area(2.0, None) is None


def test_capacitance_per_unit_area_both_none_returns_none():
    assert full_electrode_capacitance_per_unit_area(None, None) is None


def test_capacitance_per_unit_area_negative_liquid_returns_none():
    assert full_electrode_capacitance_per_unit_area(-1.0, 0.5) is None


def test_capacitance_per_unit_area_negative_filler_returns_none():
    assert full_electrode_capacitance_per_unit_area(2.0, -0.5) is None


def test_capacitance_per_unit_area_equal_returns_none():
    assert full_electrode_capacitance_per_unit_area(1.5, 1.5) is None


def test_capacitance_per_unit_area_liquid_less_than_filler_returns_none():
    assert full_electrode_capacitance_per_unit_area(0.3, 0.5) is None


def test_capacitance_per_unit_area_normal_case():
    assert full_electrode_capacitance_per_unit_area(2.0, 0.5) == 1.5


# ---------------------------------------------------------------------------
# current_capacitance_per_unit_area — reads from app globals where the device
# viewer's CalibrationModel publishes the measured capacitances.
# ---------------------------------------------------------------------------


def test_current_reads_both_from_globals(monkeypatch):
    monkeypatch.setattr(
        force_math,
        "app_globals",
        _FakeGlobals(
            liquid_capacitance_over_area=2.0,
            filler_capacitance_over_area=0.5,
        ),
    )
    assert current_full_electrode_capacitance_per_unit_area() == 1.5


def test_current_missing_global_returns_none(monkeypatch):
    monkeypatch.setattr(
        force_math,
        "app_globals",
        _FakeGlobals(
            liquid_capacitance_over_area=2.0,
            # filler absent → get() returns None → guard returns None
        ),
    )
    assert current_full_electrode_capacitance_per_unit_area() is None


def test_current_empty_globals_returns_none(monkeypatch):
    monkeypatch.setattr(force_math, "app_globals", _FakeGlobals())
    assert current_full_electrode_capacitance_per_unit_area() is None

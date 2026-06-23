"""Tests for force_math helpers (guards + behaviour).

The legacy ForceCalculationService parity tests were dropped in PPT-9 (#371)
when protocol_grid was deleted; force_math is now the sole implementation and
the behavioural cases below pin its outputs directly."""

import pytest

from dropbot_protocol_controls.services import force_math
from dropbot_protocol_controls.services.force_math import (
    full_electrode_capacitance_per_unit_area,
    current_full_electrode_capacitance_per_unit_area,
    force_for_step,
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


def test_force_for_step_zero_voltage_returns_none():
    assert force_for_step(0, 1.5) is None


def test_force_for_step_negative_voltage_returns_none():
    assert force_for_step(-10, 1.5) is None


def test_force_for_step_zero_c_per_a_returns_none():
    assert force_for_step(100, 0) is None


def test_force_for_step_negative_c_per_a_returns_none():
    assert force_for_step(100, -1.0) is None


def test_force_for_step_returns_positive_float():
    result = force_for_step(100, 1.5)
    assert result is not None
    assert isinstance(result, float)
    assert result > 0


# ---------------------------------------------------------------------------
# current_capacitance_per_unit_area — reads from app globals where the device
# viewer's CalibrationModel publishes the measured capacitances.
# ---------------------------------------------------------------------------

def test_current_reads_both_from_globals(monkeypatch):
    monkeypatch.setattr(force_math, "app_globals", _FakeGlobals(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    ))
    assert current_full_electrode_capacitance_per_unit_area() == 1.5


def test_current_missing_global_returns_none(monkeypatch):
    monkeypatch.setattr(force_math, "app_globals", _FakeGlobals(
        liquid_capacitance_over_area=2.0,
        # filler absent → get() returns None → guard returns None
    ))
    assert current_full_electrode_capacitance_per_unit_area() is None


def test_current_empty_globals_returns_none(monkeypatch):
    monkeypatch.setattr(force_math, "app_globals", _FakeGlobals())
    assert current_full_electrode_capacitance_per_unit_area() is None

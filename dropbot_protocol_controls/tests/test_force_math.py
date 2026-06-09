"""Tests for force_math helpers — guards plus parity with the legacy
ForceCalculationService that PPT-9 will eventually retire."""

import pytest

from dropbot_protocol_controls.services import force_math
from dropbot_protocol_controls.services.force_math import (
    full_electrode_capacitance_per_unit_area,
    current_full_electrode_capacitance_per_unit_area,
    force_for_step,
)
from protocol_grid.services.force_calculation_service import (
    ForceCalculationService,
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


@pytest.mark.parametrize("liquid,filler", [
    (2.0, 0.5),
    (3.5, 1.0),
    (1.5, 0.25),
    (5.0, 4.99),
])
def test_capacitance_per_unit_area_legacy_parity(liquid, filler):
    assert full_electrode_capacitance_per_unit_area(liquid, filler) == pytest.approx(
        ForceCalculationService.calculate_capacitance_per_unit_area(
            liquid, filler,
        ),
        abs=1e-6,
    )


@pytest.mark.parametrize("voltage,c_per_a", [
    (75, 1.5),
    (100, 2.0),
    (120, 0.8),
    (50, 3.0),
    (200, 1.25),
])
def test_force_for_step_legacy_parity(voltage, c_per_a):
    assert force_for_step(voltage, c_per_a) == pytest.approx(
        ForceCalculationService.calculate_force_for_step(voltage, c_per_a),
        abs=1e-6,
    )


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

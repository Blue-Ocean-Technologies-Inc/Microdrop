from typing import Optional

from microdrop_utils.ureg_helpers import ureg

from microdrop_application.helpers import get_microdrop_redis_globals_manager

app_globals = get_microdrop_redis_globals_manager()


def full_electrode_capacitance_per_unit_area(
    liquid_pf_per_mm2: Optional[float],
    filler_pf_per_mm2: Optional[float],
) -> Optional[float]:
    """Difference in pF/mm^2, or None when inputs are missing /
    negative / not strictly increasing (matches legacy guards in
    protocol_grid.services.force_calculation_service).

    Pure: depends only on its arguments. Callers that want the live
    measured calibration should use current_capacitance_per_unit_area().
    """
    if (
        liquid_pf_per_mm2 is None
        or filler_pf_per_mm2 is None
        or liquid_pf_per_mm2 < 0
        or filler_pf_per_mm2 < 0
    ):
        return None
    if liquid_pf_per_mm2 <= filler_pf_per_mm2:
        return None
    return liquid_pf_per_mm2 - filler_pf_per_mm2


def current_full_electrode_capacitance_per_unit_area() -> Optional[float]:
    """capacitance_per_unit_area for the latest measured calibration.

    Reads liquid/filler capacitances from the process-wide app globals,
    where the device viewer's CalibrationModel publishes them, so the
    Force column gets live calibration without holding its own reference
    to the calibration model. Returns None until both are present and
    valid.
    """
    return capacitance_per_unit_area(
        app_globals.get("liquid_capacitance_over_area"),
        app_globals.get("filler_capacitance_over_area"),
    )


def force_for_step(
    voltage_v: float,
    c_per_a_pf_per_mm2: float,
) -> Optional[float]:
    """F = (C/A * V^2) / 2 in mN/m, or None when inputs are
    non-positive or the resulting force is non-positive."""
    if voltage_v <= 0 or c_per_a_pf_per_mm2 <= 0:
        return None
    cap = ureg.Quantity(c_per_a_pf_per_mm2, "pF/mm**2")
    v = ureg.Quantity(voltage_v, "V")
    force = (cap * v**2 / 2).to("mN/m").magnitude
    return force if force > 0 else None

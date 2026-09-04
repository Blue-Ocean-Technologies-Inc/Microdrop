# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure DMF electrode-force math, shared by every plugin that displays the
applied force on a drop (Force protocol column, DropBot status controls).

Owned here (rather than by any one plugin) because it has more than one
caller across plugins — see issue #610. Only the pure formula lives here;
the app-globals-backed calibration lookup
(``current_full_electrode_capacitance_per_unit_area``) stays in
``dropbot_protocol_controls.services.force_math``, which owns that
Redis-backed state.
"""

# Standard library imports.
from typing import Optional

# Microdrop utils imports.
from microdrop_utils.ureg_helpers import ureg


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

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Repeat-duration / trail-overlay reconciliation, driven by the dock pane's
``cell_changed`` observer on every cell edit.

Mirrors the DV sidebar's coupling between Route Reps and Route Reps Dur (and
the dynamic Trail Overlay bound) so the protocol tree's own knobs stay in
lockstep with the same geometry math the device viewer uses to preview a
step. Pure row/manager math -- no Traits, no Qt, no broker -- testable as
plain Python.
"""

# Microdrop package imports.
from pluggable_protocol_tree.consts import REPEAT_DURATION_RECALC_TRIGGERS
from pluggable_protocol_tree.services.phase_math import (
    effective_repetitions_for_duration,
    estimate_repeat_duration_s,
    slug_shape_for_row,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Route-Reps-Dur auto-recalc: display rounding + write-back tolerance that
#: stops estimate jitter from dirtying the cell.
REPEAT_DURATION_DECIMALS = 2
REPEAT_DURATION_TOLERANCE_S = 0.01


def clamp_trail_overlay_for_row(manager, path, col_id):
    """Mirror the DV sidebar's dynamic bound (trail_overlay can never
    reach trail_length): shrinking Trail Len drags an out-of-range
    Trail Overlay down with it. Runs before the repeat-duration
    reconciliation so the recalc sees the clamped overlay."""

    if col_id != "trail_length":
        return

    try:
        row = manager.get_row(tuple(path))
    except (IndexError, AttributeError):
        return

    max_overlay = max(0, int(getattr(row, "trail_length", 1) or 1) - 1)

    if int(getattr(row, "trail_overlay", 0) or 0) > max_overlay:
        row.trail_overlay = max_overlay
        manager.cell_changed = {"path": tuple(path), "col_id": "trail_overlay"}


def reconcile_repeat_duration_for_row(manager, path, col_id, is_protocol_active):
    """Mirror the legacy auto-recalc / effective-reps coupling:

      * In Route-Reps-controlled mode (``repeat_duration_controls``
        False): edits to any geometry/timing knob refresh the
        Route Reps Dur cell with the new estimate.
      * In Route-Reps-Dur-controlled mode (flag True): edits to
        Route Reps Dur refresh the Route Reps cell with the effective
        number of full cycles that fit.

    Skipped while a run is active (``is_protocol_active``) -- an executing
    protocol owns its own timing, not a cell-edit reconciliation pass.

    Programmatic writes here go via ``setattr`` directly (NOT
    ``model.set_value`` and NOT through ``on_interact``) so the
    mode-switch dialog only ever fires for genuine user clicks,
    never for these reconciliation passes.
    """

    if is_protocol_active:
        return

    try:
        row = manager.get_row(tuple(path))
    except (IndexError, AttributeError):
        return

    routes = list(getattr(row, "routes", []) or [])

    if not routes:
        return

    controls = bool(getattr(row, "repeat_duration_controls", False))
    duration_s = float(getattr(row, "duration_s", 1.0) or 0.0)
    trail_length = int(getattr(row, "trail_length", 1) or 1)
    trail_overlay = int(getattr(row, "trail_overlay", 0) or 0)
    linear_repeats = bool(getattr(row, "linear_repeats", False))
    soft_start = bool(getattr(row, "soft_start", False))
    soft_end = bool(getattr(row, "soft_end", False))

    if not controls and col_id in REPEAT_DURATION_RECALC_TRIGGERS:
        n_repeats = int(getattr(row, "route_repetitions", 1) or 1)
        estimated = estimate_repeat_duration_s(
            routes=routes,
            trail_length=trail_length,
            trail_overlay=trail_overlay,
            n_repeats=n_repeats,
            step_duration_s=duration_s,
            linear_repeats=linear_repeats,
            soft_start=soft_start,
            soft_end=soft_end,
            **slug_shape_for_row(row),
        )
        estimated = round(estimated, REPEAT_DURATION_DECIMALS)
        current = float(getattr(row, "repeat_duration", 0.0))

        if abs(current - estimated) >= REPEAT_DURATION_TOLERANCE_S:
            row.repeat_duration = estimated
            # Re-entrancy is bounded: see the
            # REPEAT_DURATION_RECALC_TRIGGERS guard + mode-check above;
            # "repeat_duration" is not a trigger in
            # route-reps-controlled mode so the next pass exits cleanly.
            manager.cell_changed = {
                "path": tuple(path),
                "col_id": "repeat_duration",
            }

    elif controls and col_id == "repeat_duration":
        effective = effective_repetitions_for_duration(
            routes=routes,
            trail_length=trail_length,
            trail_overlay=trail_overlay,
            step_duration_s=duration_s,
            repeat_duration_s=float(getattr(row, "repeat_duration", 0.0) or 0.0),
            **slug_shape_for_row(row),
        )

        if int(getattr(row, "route_repetitions", 1) or 1) != int(effective):
            row.route_repetitions = int(effective)
            manager.cell_changed = {
                "path": tuple(path),
                "col_id": "route_repetitions",
            }

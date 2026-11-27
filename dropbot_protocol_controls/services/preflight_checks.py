# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pre-flight checks of the voltage and frequency columns: the DropBot's
connection and power, its chip, and the run's setpoints against the active
device's range.

The connection and chip checks read app_globals once. This plugin loads
with every backend, and only the DropBot's (or its mock) writes those keys
(the connection state as it starts, deleted on a clean stop), so a missing
value means no DropBot backend and skips its check. The range check takes
the same device range the column's cells are bounded by, which every
backend writes, so it judges any device. None blocks a run: a hard kill can
leave a stale key, so a disconnected DropBot, a missing chip or a setpoint
outside the range only warns.
"""

# Microdrop package imports.
from dropbot_controller.consts import (
    DROPBOT_CHIP_INSERTED_KEY,
    DROPBOT_CONNECTION_STATE_KEY,
    DROPBOT_NO_POWER_KEY,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from pluggable_protocol_tree.preflight.checks import (
    ColumnCheck,
    Result,
    run_actuates_electrodes,
    step_name,
)

# Local imports.
from ..consts import PREFLIGHT_CHIP_CHECK, PREFLIGHT_DROPBOT_CHECK

#: Every check here judges hardware, which a preview never drives.
PREVIEW_SKIP = Result(
    status="skip", detail="Preview", tooltip="Preview drives no hardware."
)

#: The chip check needs a connected DropBot.
NEEDS_DROPBOT = Result(
    status="skip", detail="No DropBot", tooltip="Needs a connected DropBot."
)

#: A run actuating no electrode needs no chip.
NO_ELECTRODES_SKIP = Result(
    status="skip",
    detail="No electrodes",
    tooltip="No run step names electrodes or routes, so it needs no chip.",
)


def dropbot_connection_check(context):
    """Whether a powered DropBot is connected; skipped when no DropBot
    backend has reported a connection state (a mock, portable or OpenDrop
    rig)."""
    if context.preview_mode:
        result = PREVIEW_SKIP

    else:
        app_globals = get_microdrop_redis_globals_manager()
        result = _connection_result(
            app_globals.get(DROPBOT_CONNECTION_STATE_KEY),
            app_globals.get(DROPBOT_NO_POWER_KEY),
        )

    return ColumnCheck(
        id=PREFLIGHT_DROPBOT_CHECK, label="DropBot", result=result, category="Hardware"
    )


def chip_check(context):
    """Whether the connected DropBot has a chip inserted, for a run whose
    steps name electrodes or routes; skipped while no DropBot is connected
    or its chip has not been read."""
    if context.preview_mode:
        result = PREVIEW_SKIP

    elif not run_actuates_electrodes(context):
        result = NO_ELECTRODES_SKIP

    else:
        result = _chip_result(get_microdrop_redis_globals_manager())

    return ColumnCheck(
        id=PREFLIGHT_CHIP_CHECK, label="Chip", result=result, category="Hardware"
    )


def device_range_check(context, check_id, label, column_id, device_range, unit):
    """Whether every run step's ``column_id`` setpoint is within
    ``device_range``, the active device's ``(low, high)`` that also bounds
    the column's cells."""
    if context.preview_mode:
        result = PREVIEW_SKIP

    else:
        result = _range_result(context, column_id, device_range, unit, label)

    return ColumnCheck(id=check_id, label=label, result=result, category="Hardware")


def _connection_result(connected, no_power):
    if connected is None:
        return Result(
            status="skip",
            detail="No DropBot",
            tooltip="No DropBot backend reports a connection.",
        )

    if connected:
        return Result(status="pass")

    if no_power:
        tooltip = (
            "The DropBot answers on USB but has no power: connect its supply "
            "and retry the connection, or the run will time out at its first "
            "step."
        )

        return Result(
            status="warn", detail="Not connected", tooltip=tooltip, problem="No power"
        )

    tooltip = "No DropBot is connected, so the run will time out at its first step."

    return Result(
        status="warn",
        detail="Not connected",
        tooltip=tooltip,
        problem="DropBot disconnected",
    )


def _chip_result(app_globals):
    if not app_globals.get(DROPBOT_CONNECTION_STATE_KEY):
        return NEEDS_DROPBOT

    inserted = app_globals.get(DROPBOT_CHIP_INSERTED_KEY)

    if inserted is None:
        return Result(
            status="skip",
            detail="Not read yet",
            tooltip="The DropBot has not reported whether a chip is inserted.",
        )

    if not inserted:
        return Result(
            status="warn",
            detail="Not inserted",
            tooltip="The run will actuate nothing.",
            problem="No chip inserted",
        )

    return Result(status="pass")


def _range_result(context, column_id, device_range, unit, label):
    """A warning on the first run step outside ``device_range``, else a pass."""
    low, high = device_range

    for step in context.run_steps():
        value = step.get(column_id)

        if value is not None and not low <= value <= high:
            name = step_name(step)
            tooltip = (
                f"{name}: {value} {unit} is outside the device's "
                f"{low}-{high} {unit} range."
            )

            return Result(
                status="warn",
                detail=name,
                tooltip=tooltip,
                problem=f"{label} out of range",
            )

    return Result(status="pass")

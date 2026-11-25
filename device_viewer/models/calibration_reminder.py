# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""When to remind the user to calibrate, and what the reminder says.
Pure functions of the saved calibration and today's date; Qt-free."""

# Standard library imports.
from datetime import date

# Local imports.
from ..consts import CALIBRATION_STALE_DAYS

#: The calibration's states, worst first.
CALIBRATION_MISSING = "missing"
CALIBRATION_DATE_UNKNOWN = "date unknown"
CALIBRATION_STALE = "stale"
CALIBRATION_FRESH = "fresh"

#: Within Needs attention: a missing calibration above an old one.
MISSING_PRIORITY = 2
STALE_PRIORITY = 1

#: What a fresh calibration resolves the reminder with.
CALIBRATED_RESOLUTION = "Calibrated"

_RECALIBRATE = (
    "Recalibrate before quantitative runs: capacitance readings drift over time."
)


def reminder_state(
    liquid, filler, calibrated_on, today, stale_days=CALIBRATION_STALE_DAYS
):
    """The calibration's state and its age in days (None when unknown).

    Parameters
    ----------
    liquid, filler
        The saved capacitances over area; None when not measured.
    calibrated_on
        The day it was measured, ISO ("2026-11-25"); empty when unknown (a
        calibration saved before dates were).
    today
        A ``datetime.date``.
    stale_days
        Older than this many days, a calibration is stale.
    """

    if liquid is None or filler is None:
        return CALIBRATION_MISSING, None

    try:
        age = (today - date.fromisoformat(calibrated_on)).days

    except (TypeError, ValueError):
        return CALIBRATION_DATE_UNKNOWN, None

    if age > stale_days:
        return CALIBRATION_STALE, age

    return CALIBRATION_FRESH, age


def reminder_text(state, age):
    """The reminder's ``(title, detail, priority)`` for ``state``; None when
    fresh (no reminder)."""

    if state == CALIBRATION_MISSING:
        return (
            "No calibration saved",
            "Capacitance-based volume and position readings need a calibration. "
            "Calibrate before quantitative runs.",
            MISSING_PRIORITY,
        )

    if state == CALIBRATION_DATE_UNKNOWN:
        return (
            "Calibration date unknown",
            f"It was saved before MicroDrop recorded dates. {_RECALIBRATE}",
            STALE_PRIORITY,
        )

    if state == CALIBRATION_STALE:
        return (f"Calibration is {age} days old", _RECALIBRATE, STALE_PRIORITY)

    return None

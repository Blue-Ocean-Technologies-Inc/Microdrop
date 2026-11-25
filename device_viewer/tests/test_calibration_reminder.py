# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The calibration reminder: missing is worse than an unknown date or an old
calibration, and a fresh one needs no reminder."""

# Standard library imports.
from datetime import date

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.consts import CALIBRATION_STALE_DAYS
from device_viewer.models.calibration_reminder import (
    CALIBRATION_DATE_UNKNOWN,
    CALIBRATION_FRESH,
    CALIBRATION_MISSING,
    CALIBRATION_STALE,
    MISSING_PRIORITY,
    STALE_PRIORITY,
    reminder_state,
    reminder_text,
)

TODAY = date(2026, 11, 25)


@pytest.mark.parametrize("liquid, filler", [(None, None), (2.0, None), (None, 0.5)])
def test_a_value_not_measured_is_missing(liquid, filler):
    assert reminder_state(liquid, filler, "2026-11-25", TODAY) == (
        CALIBRATION_MISSING,
        None,
    )


@pytest.mark.parametrize("calibrated_on", ["", "not a date", None])
def test_a_calibration_without_a_date_is_not_missing(calibrated_on):
    assert reminder_state(2.0, 0.5, calibrated_on, TODAY) == (
        CALIBRATION_DATE_UNKNOWN,
        None,
    )


def test_a_calibration_is_fresh_up_to_the_threshold():
    calibrated_on = date.fromordinal(TODAY.toordinal() - CALIBRATION_STALE_DAYS)

    assert reminder_state(2.0, 0.5, calibrated_on.isoformat(), TODAY) == (
        CALIBRATION_FRESH,
        CALIBRATION_STALE_DAYS,
    )


def test_a_calibration_older_than_the_threshold_is_stale():
    assert reminder_state(2.0, 0.5, "2026-11-16", TODAY) == (CALIBRATION_STALE, 9)


def test_the_reminder_says_how_old_and_ranks_missing_first():
    title, _detail, priority = reminder_text(CALIBRATION_STALE, 9)
    missing_title, _detail, missing_priority = reminder_text(CALIBRATION_MISSING, None)

    assert title == "Calibration is 9 days old"
    assert missing_title == "No calibration saved"
    assert missing_priority == MISSING_PRIORITY > priority == STALE_PRIORITY
    assert reminder_text(CALIBRATION_FRESH, 2) is None

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Entry times read relative to now: "just now", minutes, then the clock
time today and the date on other days; the exact time stays available."""

# Standard library imports.
from datetime import datetime

# Third-party imports.
import pytest

# Microdrop package imports.
from notifications.views.formatting import format_exact_time, format_time

#: The injected clock: 15:00 local time on a fixed day.
NOW = datetime(2026, 11, 23, 15, 0, 0).timestamp()


@pytest.mark.parametrize(
    "age_s, expected",
    [
        (0, "just now"),
        (59, "just now"),
        (60, "1 min ago"),
        (59 * 60 + 59, "59 min ago"),
        (60 * 60, "14:00"),
        (14 * 60 * 60 + 59 * 60, "00:01"),
        (15 * 60 * 60 + 1, "2026-11-22"),
    ],
)
def test_times_read_relative_to_the_clock(age_s, expected):
    assert format_time(NOW - age_s, now=NOW) == expected


def test_a_time_ahead_of_the_clock_reads_just_now():
    assert format_time(NOW + 5, now=NOW) == "just now"


def test_the_exact_time_has_date_and_seconds():
    assert format_exact_time(NOW - 1) == "2026-11-23 14:59:59"

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""When to remind the user to run the DropBot self tests, and what the
reminder says: pure functions of the last completed run and today's date.
Qt-free."""

# Standard library imports.
from datetime import datetime

# Local imports.
from .consts import SELF_TEST_STALE_DAYS

#: The self test's states, worst first.
SELF_TEST_NEVER_RUN = "never run"
SELF_TEST_STALE = "stale"
SELF_TEST_FRESH = "fresh"

#: Within Needs attention: never run above an old run.
NEVER_RUN_PRIORITY = 2
STALE_PRIORITY = 1

_CHECK = (
    "Check the high-voltage output, channels and chip connections before your "
    "next experiment: Tools › Dropbot › Run all on-board self-tests, "
    "with the test board in."
)


def reminder_state(last_run, today, stale_days=SELF_TEST_STALE_DAYS):
    """The self test's state and the last run's age in days (None when
    never run).

    Parameters
    ----------
    last_run
        When the last full run completed, ISO ("2026-11-25T10:30:00");
        empty (or unreadable) when never.
    today
        A ``datetime.date``.
    stale_days
        A run older than this many days is stale.
    """

    try:
        age = (today - datetime.fromisoformat(last_run).date()).days

    except (TypeError, ValueError):
        return SELF_TEST_NEVER_RUN, None

    if age > stale_days:
        return SELF_TEST_STALE, age

    return SELF_TEST_FRESH, age


def reminder_text(state, age):
    """The reminder's ``(title, detail, priority)`` for ``state``; None when
    fresh (no reminder)."""

    if state == SELF_TEST_NEVER_RUN:
        return ("Self test has not been run", _CHECK, NEVER_RUN_PRIORITY)

    if state == SELF_TEST_STALE:
        return (f"Self test last run {age} days ago", _CHECK, STALE_PRIORITY)

    return None


def session_resolution(failed_tests):
    """What a completed run resolves the reminder with."""

    if failed_tests:
        return f"Self test finished · {failed_tests} failed"

    return "Self test passed"


def is_full_run(tests):
    """Whether a session of ``tests`` (names) is the full suite: a single
    test is started from its own menu entry, the full suite runs them all."""
    return len(tests or ()) > 1

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test reminder: never run is worse than an old run, a recent run
needs no reminder, and only the full suite counts as a run."""

# Standard library imports.
from datetime import date

# Third-party imports.
import pytest

# Microdrop package imports.
from dropbot_tools_menu.consts import SELF_TEST_STALE_DAYS
from dropbot_tools_menu.self_test_reminder import (
    NEVER_RUN_PRIORITY,
    SELF_TEST_FRESH,
    SELF_TEST_NEVER_RUN,
    SELF_TEST_STALE,
    STALE_PRIORITY,
    is_full_run,
    reminder_state,
    reminder_text,
    session_resolution,
)

TODAY = date(2026, 11, 25)


@pytest.mark.parametrize("last_run", ["", "garbage", None])
def test_no_readable_last_run_is_never_run(last_run):
    assert reminder_state(last_run, TODAY) == (SELF_TEST_NEVER_RUN, None)


def test_a_run_is_fresh_up_to_the_threshold():
    last_run = date.fromordinal(TODAY.toordinal() - SELF_TEST_STALE_DAYS)

    assert reminder_state(f"{last_run.isoformat()}T09:00:00", TODAY) == (
        SELF_TEST_FRESH,
        SELF_TEST_STALE_DAYS,
    )


def test_a_run_older_than_the_threshold_is_stale():
    assert reminder_state("2026-11-13T17:45:00", TODAY) == (SELF_TEST_STALE, 12)


def test_the_reminder_says_how_old_and_ranks_never_run_first():
    title, _detail, priority = reminder_text(SELF_TEST_STALE, 12)
    never_title, _detail, never_priority = reminder_text(SELF_TEST_NEVER_RUN, None)

    assert title == "Self test last run 12 days ago"
    assert never_title == "Self test has not been run"
    assert never_priority == NEVER_RUN_PRIORITY > priority == STALE_PRIORITY
    assert reminder_text(SELF_TEST_FRESH, 3) is None


def test_only_the_full_suite_counts_as_a_run():
    assert is_full_run(["system_info", "test_voltage", "test_channels"])
    assert not is_full_run(["test_voltage"])
    assert not is_full_run(None)


def test_a_run_resolves_with_its_outcome():
    assert session_resolution(0) == "Self test passed"
    assert session_resolution(2) == "Self test finished · 2 failed"


def test_without_a_dropbot_the_reminder_says_to_connect_one():
    _title, disconnected, _priority = reminder_text(SELF_TEST_STALE, 12)
    _title, connected, _priority = reminder_text(SELF_TEST_STALE, 12, connected=True)

    assert "Connect a DropBot first" in disconnected
    assert "Connect a DropBot first" not in connected

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The bell: Needs attention entries count until resolved, read or not;
other entries while unread and not on screen as toasts. Its colour: an
unread error's, else the Needs attention orange, else the worst unread."""

# Standard library imports.
from types import SimpleNamespace

# Microdrop package imports.
from notifications.consts import SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING
from notifications.models.notifications_pane_model import (
    ALERT_SEVERITY,
    bell_summary,
)
from notifications.models.own_sections import ATTENTION_ACCENT


def entry(severity=SEVERITY_INFO, unread=True, needs_attention=False):
    return SimpleNamespace(
        severity=severity,
        unread=unread,
        needs_attention=needs_attention,
        section_id="",
        alert=None,
        accent=(),
    )


def test_nothing_counts_when_all_is_read_and_nothing_needs_attention():
    assert bell_summary([entry(unread=False)], set()) == (0, "", (), 0, 0)


def test_read_needs_attention_entries_still_count_in_orange():
    reminders = [
        entry(SEVERITY_WARNING, unread=False, needs_attention=True),
        entry(SEVERITY_WARNING, unread=False, needs_attention=True),
    ]

    assert bell_summary(reminders, set()) == (
        2,
        ALERT_SEVERITY,
        ATTENTION_ACCENT,
        2,
        0,
    )


def test_unread_entries_add_to_the_needs_attention_count():
    entries = [
        entry(SEVERITY_WARNING, unread=False, needs_attention=True),
        entry(),
        entry(),
    ]
    count, severity, _accent, attention, new = bell_summary(entries, set())

    assert (count, attention, new) == (3, 1, 2)
    assert severity == ALERT_SEVERITY


def test_an_unread_error_colours_the_bell_red():
    entries = [entry(SEVERITY_WARNING, needs_attention=True), entry(SEVERITY_ERROR)]

    assert bell_summary(entries, set())[1] == SEVERITY_ERROR


def test_an_entry_on_screen_as_a_toast_waits_for_the_bell():
    toast = entry(SEVERITY_WARNING)

    assert bell_summary([toast], {id(toast)})[0] == 0
    assert bell_summary([toast], set())[:2] == (1, SEVERITY_WARNING)

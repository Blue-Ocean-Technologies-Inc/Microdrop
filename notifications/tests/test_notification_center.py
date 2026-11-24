# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications model: posting, collapsing repeats, the entry cap, the
unread state, and the pane model's header and sections."""

# Microdrop package imports.
from notifications.consts import (
    SEVERITY_ERROR,
    SEVERITY_SUCCESS,
    SEVERITY_WARNING,
    TITLE_MAX_CHARS,
    NotificationMessage,
    NotificationSection,
    OpenPathAction,
)
from notifications.models.notification_center import (
    NotificationCenter,
    title_and_detail,
)
from notifications.models.notifications_pane_model import NotificationsPaneModel


def test_new_notifications_list_newest_first_and_unread():
    center = NotificationCenter()

    center.post("First", timestamp=1.0)
    center.post("Second", timestamp=2.0)

    assert [entry.title for entry in center.entries] == ["Second", "First"]
    assert center.unread_count == 2


def test_a_repeat_collapses_into_its_entry_and_moves_to_the_top():
    center = NotificationCenter()
    repeated = center.post("Disk almost full", detail="90 %", timestamp=1.0)
    center.post("Other", timestamp=2.0)
    center.mark_all_read()

    again = center.post("Disk almost full", detail="95 %", timestamp=3.0)

    assert again is repeated
    assert center.entries[0] is repeated
    assert len(center.entries) == 2
    assert repeated.count == 2
    assert repeated.detail == "95 %"
    assert (repeated.first_seen, repeated.last_seen) == (1.0, 3.0)
    assert repeated.unread
    assert center.unread_count == 1


def test_notifications_differing_in_severity_do_not_collapse():
    center = NotificationCenter()

    center.post("Pump", severity=SEVERITY_WARNING)
    center.post("Pump", severity=SEVERITY_ERROR)

    assert len(center.entries) == 2


def test_past_the_cap_the_oldest_entry_goes_and_can_come_back_new():
    center = NotificationCenter(max_entries=3)

    for number in range(5):
        center.post(f"n{number}", timestamp=float(number))

    assert [entry.title for entry in center.entries] == ["n4", "n3", "n2"]

    again = center.post("n0")

    assert again.count == 1
    assert len(center.entries) == 3


def test_unread_severity_is_the_most_urgent_unread_one():
    center = NotificationCenter()
    center.post("ok", severity=SEVERITY_SUCCESS)
    error = center.post("bad", severity=SEVERITY_ERROR)

    assert center.unread_severity == SEVERITY_ERROR

    error.unread = False

    assert center.unread_severity == SEVERITY_SUCCESS

    center.mark_all_read()

    assert center.unread_severity == ""
    assert center.unread_count == 0


def test_dismiss_and_clear_forget_the_entries_keys():
    center = NotificationCenter()
    entry = center.post("Once")
    center.post("Twice")

    center.dismiss(entry)

    assert center.post("Once").count == 1

    center.clear()

    assert center.entries == []
    assert center.post("Twice").count == 1


def test_a_long_or_multi_line_text_gives_a_short_title_and_keeps_it_all():
    long_text = "x" * (TITLE_MAX_CHARS + 20)

    title, detail = title_and_detail(long_text)

    assert len(title) == TITLE_MAX_CHARS
    assert title.endswith("…")
    assert detail == long_text

    title, detail = title_and_detail("First line\nsecond line", "Traceback ...")

    assert title == "First line"
    assert detail == "First line\nsecond line\n\nTraceback ..."
    assert title_and_detail("Just a line") == ("Just a line", "")


def test_a_posted_message_keeps_its_fields_and_action():
    center = NotificationCenter()
    message = NotificationMessage(
        title="Report ready",
        detail="Steps: 12",
        severity=SEVERITY_SUCCESS,
        category="protocol",
        source="pluggable_protocol_tree",
        timestamp=5.0,
        action={"kind": "open_path", "label": "Open", "path": "C:/report.html"},
    )

    entry = center.post_message(message)

    assert (entry.title, entry.detail) == ("Report ready", "Steps: 12")
    assert (entry.category, entry.source) == ("protocol", "pluggable_protocol_tree")
    assert entry.last_seen == 5.0
    assert isinstance(entry.action, OpenPathAction)
    assert not entry.monospace_detail


def test_a_traceback_detail_shows_monospace():
    center = NotificationCenter()

    entry = center.post("Boom", detail="Traceback (most recent call last):\n ...")

    assert entry.monospace_detail


def test_the_header_counts_new_and_total():
    model = NotificationsPaneModel()

    assert model.header_text == "No notifications"

    model.center.post("a")
    model.center.post("b")

    assert model.header_text == "2 new of 2"

    model.center.mark_all_read()

    assert model.header_text == "2 notifications"


def test_sections_show_in_order_and_expand_by_id():
    late = NotificationSection(id="late", title="Late", order=5)
    early = NotificationSection(id="early", title="Early", order=1)
    model = NotificationsPaneModel(sections=[late, early])

    assert model.ordered_sections == [early, late]

    model.expand_section("late")

    assert late.expanded
    assert not early.expanded

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Dialogs recorded in the notifications drawer: which are recorded, the
quiet entry built from a dialog's title and text, and how repeats count."""

# Microdrop package imports.
from microdrop_application.dialogs.consts import (
    DIALOG_DETAIL_MAX_CHARS,
    DIALOG_REPEAT_WINDOW_S,
    DIALOG_SOURCE,
)
from microdrop_application.dialogs.dialog_records import (
    dialog_notification,
    dialog_occurrence,
    plain_text,
    record_from_kwargs,
)
from notifications.consts import (
    CATEGORY_ID_DIALOG_ALERTS,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    NotificationMessage,
)


def test_markup_is_stripped_and_plain_text_kept_as_is():
    rich = "DropBot has halted.<br><br>All channels &amp; HV <b>off</b>."
    traceback = "Traceback (most recent call last):\n  File 'x.py'"

    assert plain_text(rich) == "DropBot has halted.\n\nAll channels & HV off."
    assert plain_text(traceback) == traceback
    assert plain_text("a < b and c > d") == "a < b and c > d"


def test_a_dialog_entry_is_quiet_listed_and_validates():
    payload = dialog_notification(
        SEVERITY_ERROR,
        "DropBot Halted",
        "DropBot has halted.<br>Restart it.",
        source="dropbot_status_and_controls",
        help_target="dropbot_status#dlg-halted",
        occurrence="1.000",
    )
    message = NotificationMessage.model_validate(payload)

    assert (message.title, message.detail) == (
        "DropBot Halted",
        "DropBot has halted.\nRestart it.",
    )
    assert not message.pop_up
    assert message.category_id == CATEGORY_ID_DIALOG_ALERTS
    assert message.secondary_action.target == "dropbot_status#dlg-halted"


def test_a_generic_title_gives_way_to_the_first_line():
    payload = dialog_notification(
        SEVERITY_WARNING, "Warning", "Layout not saved\nThe disk is full."
    )

    assert (payload["title"], payload["detail"]) == (
        "Layout not saved",
        "The disk is full.",
    )
    assert payload["source"] == DIALOG_SOURCE


def test_a_long_detail_is_cut():
    payload = dialog_notification(SEVERITY_ERROR, "Boom", "x" * 10_000)

    assert len(payload["detail"]) == DIALOG_DETAIL_MAX_CHARS


def test_a_burst_is_one_occurrence_and_a_later_showing_a_new_one():
    first = dialog_occurrence(None, 100.0)
    burst = dialog_occurrence((first, 100.0), 100.0 + DIALOG_REPEAT_WINDOW_S)
    later = dialog_occurrence((first, 100.0), 101.0 + DIALOG_REPEAT_WINDOW_S)

    assert burst == first
    assert later != first


def test_the_recording_keywords_leave_the_dialog_keywords(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        "microdrop_application.dialogs.dialog_records.record_dialog",
        lambda *args: recorded.append(args),
    )
    kwargs = {"record": False, "source": "x", "help_target": "y", "checkbox_text": "z"}

    record_from_kwargs(kwargs, SEVERITY_ERROR, "Error", "Failed")

    assert kwargs == {"checkbox_text": "z"}
    assert recorded == []

    record_from_kwargs({}, SEVERITY_INFO, "Done", "Saved", record=False)

    assert recorded == []

    record_from_kwargs({}, SEVERITY_ERROR, "Error", "Failed")

    assert recorded == [(SEVERITY_ERROR, "Error", "Failed", None, DIALOG_SOURCE, "")]

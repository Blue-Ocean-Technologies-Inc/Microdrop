# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notification contract's additions: messages posted before them still
validate, resolving clears Needs attention, threads update one entry,
categories carry their owners' defaults, and reading many entries is one
change."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Microdrop package imports.
from notifications.consts import (
    CATEGORY_ID_LOG,
    CATEGORY_ID_PLUGIN_LOAD_FAILED,
    NOTIFICATIONS_CATEGORIES,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    TONE_SOFT,
    HelpAction,
    NotificationCategorySpec,
    NotificationMessage,
    NotificationResolveRequest,
    SnoozeAction,
)
from notifications.controllers.notifications_controller import NotificationsController
from notifications.models.notification_center import NotificationCenter

#: A payload as posted on main before the additions.
OLD_PAYLOAD = (
    '{"title": "Protocol finished", "severity": "success", "category": "protocol",'
    ' "source": "p", "timestamp": 1.0,'
    ' "action": {"kind": "publish", "label": "Open", "topic": "a/b", "message": ""}}'
)


def test_an_old_message_still_validates_with_defaults():
    message = NotificationMessage.model_validate_json(OLD_PAYLOAD)

    assert message.secondary_action is None
    assert not message.needs_attention
    assert message.category_id == message.thread_id == message.condition_id == ""


def test_a_message_carries_its_second_button():
    message = NotificationMessage.model_validate(
        {"title": "t", "secondary_action": {"kind": "help", "target": "Chips"}}
    )
    later = NotificationMessage.model_validate(
        {"title": "t", "secondary_action": {"kind": "snooze"}}
    )

    assert message.secondary_action == HelpAction(target="Chips")
    assert isinstance(later.secondary_action, SnoozeAction)

    with pytest.raises(ValidationError):
        NotificationMessage.model_validate(
            {"title": "t", "secondary_action": {"kind": "help", "target": ""}}
        )


def test_a_resolve_request_names_its_condition():
    request = NotificationResolveRequest.model_validate({"condition_id": "chip"})

    assert request.resolution == "Resolved"

    with pytest.raises(ValidationError):
        NotificationResolveRequest.model_validate({"condition_id": ""})


def test_resolving_clears_the_conditions_cards_only():
    center = NotificationCenter()
    chip = center.post("Chip out", needs_attention=True, condition_id="chip")
    other = center.post("Old calibration", needs_attention=True, condition_id="cal")

    center.resolve("chip", "Chip detected")

    assert center.attention_entries == [other]
    assert not chip.needs_attention and not chip.unread
    assert chip.acted == "Chip detected"


def test_a_thread_updates_one_entry_in_place():
    center = NotificationCenter()
    center.post("Step 1 of 3", thread_id="run")
    entry = center.post(
        "Step 2 of 3", thread_id="run", severity=SEVERITY_WARNING, detail="slow"
    )

    assert center.entries == [entry]
    assert (entry.title, entry.count, entry.severity) == ("Step 2 of 3", 1, "warning")

    # A thread's post is its whole state: what it leaves out is cleared.
    center.post("Step 3 of 3", thread_id="run")

    assert entry.detail == ""
    assert entry.severity == "info"


def test_a_repeat_while_unread_is_announced_as_a_repeat():
    center = NotificationCenter()
    arrived, repeated = [], []
    center.observe(lambda event: arrived.append(event.new), "arrived")
    center.observe(lambda event: repeated.append(event.new), "repeated")

    first = center.post("Same")
    center.post("Same")
    first.unread = False
    center.post("Same")

    assert arrived == [first, first]
    assert repeated == [first]
    assert first.count == 3


def test_categories_take_their_owners_defaults():
    center = NotificationCenter()
    center.settings.declare(NOTIFICATIONS_CATEGORIES)
    failures = center.settings.category(CATEGORY_ID_PLUGIN_LOAD_FAILED)

    assert failures.critical and failures.in_drawer
    assert center.settings.category(CATEGORY_ID_LOG).popup

    # A critical category cannot be kept out of the drawer.
    failures.in_drawer = False

    assert failures.in_drawer


def test_a_category_kept_out_of_the_drawer_records_only_what_matters():
    center = NotificationCenter()
    spec = NotificationCategorySpec(
        id="demo.steps", group="Demo", label="Steps", drawer=False, tone=TONE_SOFT
    )
    center.settings.declare([spec])

    assert center.post("Step done", category_id="demo.steps") is None
    assert center.post("Step failed", category_id="demo.steps", severity=SEVERITY_ERROR)
    assert center.post("Insert chip", category_id="demo.steps", needs_attention=True)

    # Declared again (a plugin reloaded), the user's choice stands.
    center.settings.category("demo.steps").in_drawer = True
    center.settings.declare([spec])

    assert center.settings.category("demo.steps").in_drawer


def test_marking_many_read_is_one_change():
    center = NotificationCenter()

    for number in range(300):
        center.post(f"entry {number}")

    counts, bulk = [], []
    center.observe(lambda event: counts.append(event.new), "unread_count")
    center.observe(lambda event: bulk.append(True), "bulk_changed")

    center.mark_all_read()

    assert counts == [0]
    assert bulk == [True]
    assert center.unread_count == 0


def test_what_arrives_in_the_open_drawer_never_counts_on_the_bell():
    controller = NotificationsController(publish=lambda **message: None)
    model = controller.pane_model
    model.center.post("before")

    assert model.bell_count == 1

    model.is_open = True
    model.center.post("while open")

    assert model.bell_count == 0
    assert model.center.new_count == 2

    model.is_open = False

    assert model.center.new_count == 0


def test_help_is_available_only_with_a_handler():
    controller = NotificationsController(publish=lambda **message: None)

    assert not controller.pane_model.help_available

    controller.open_help = lambda target: None

    assert controller.pane_model.help_available

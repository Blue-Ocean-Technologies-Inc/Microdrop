# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The NOTIFICATION_POST payload: what validates, what does not, and that it
crosses the broker as JSON with its action."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Microdrop package imports.
from notifications.consts import (
    NotificationMessage,
    PublishAction,
    ShowNotificationsPanelRequest,
)


def test_a_title_alone_is_an_info_notification_stamped_now():
    message = NotificationMessage(title="Hello")

    assert message.severity == "info"
    assert message.category == "general"
    assert message.timestamp > 0
    assert message.action is None


@pytest.mark.parametrize(
    "payload",
    [
        {"title": ""},
        {"title": "x", "severity": "fatal"},
        {"title": "x", "action": {"kind": "run", "label": "Go"}},
        {"title": "x", "action": {"kind": "publish", "label": "Go"}},
        {"title": "x", "action": {"kind": "open_path", "label": "", "path": "C:/"}},
    ],
)
def test_invalid_payloads_are_rejected(payload):
    with pytest.raises(ValidationError):
        NotificationMessage.model_validate(payload)


def test_the_action_survives_a_json_round_trip_as_its_own_kind():
    message = NotificationMessage(
        title="Calibrated",
        action={"kind": "publish", "label": "Redo", "topic": "a/b", "message": "1"},
    )

    copy = NotificationMessage.model_validate_json(message.model_dump_json())

    assert isinstance(copy.action, PublishAction)
    assert copy == message


def test_a_show_panel_request_names_a_section_or_none():
    assert ShowNotificationsPanelRequest().section_id == ""
    assert (
        ShowNotificationsPanelRequest.model_validate_json('{"section_id": "s"}')
    ).section_id == "s"

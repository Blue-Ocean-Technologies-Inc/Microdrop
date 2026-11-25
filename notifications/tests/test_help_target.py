# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A help link's target names a tutorial, and optionally a section in it."""

# Third-party imports.
import pytest

# Microdrop package imports.
from notifications.consts import HelpAction, help_target, parse_help_target


@pytest.mark.parametrize(
    "tutorial_id, anchor, target",
    [
        ("dropbot_status", "part-tools", "dropbot_status#part-tools"),
        ("zones", None, "zones"),
        ("zones", "", "zones"),
    ],
)
def test_a_target_round_trips(tutorial_id, anchor, target):
    assert help_target(tutorial_id, anchor) == target
    assert parse_help_target(target) == (tutorial_id, anchor or None)


def test_an_empty_anchor_is_none():
    assert parse_help_target("zones#") == ("zones", None)


def test_a_help_action_carries_its_target():
    action = HelpAction(label="What does it check?", target="dropbot_status#part-tools")

    assert parse_help_target(action.target) == ("dropbot_status", "part-tools")

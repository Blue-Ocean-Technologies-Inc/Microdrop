# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the device viewer's keyboard shortcut table and dispatch."""

# Microdrop package imports.
from device_viewer.consts import (
    ARROW_DIRECTIONS,
    KEYBOARD_SHORTCUT_GROUPS,
    KEYBOARD_SHORTCUTS,
)


def test_shortcut_sequences_are_unique():
    sequences = [row[0] for row in KEYBOARD_SHORTCUTS]

    assert len(sequences) == len(set(sequences))


def test_every_arrow_verb_has_all_four_directions():
    actions = {row[1] for row in KEYBOARD_SHORTCUTS}

    for verb in ("step", "extend", "shrink", "split", "draw_route"):
        assert {f"{verb}_{d}" for d in ARROW_DIRECTIONS} <= actions


def test_the_requested_modifier_mapping():
    by_sequence = {row[0]: row[1] for row in KEYBOARD_SHORTCUTS}

    assert by_sequence["Up"] == "step_up"
    assert by_sequence["Shift+Up"] == "extend_up"
    assert by_sequence["Ctrl+Up"] == "shrink_up"
    assert by_sequence["Alt+Up"] == "draw_route_up"
    assert by_sequence["Ctrl+Shift+Up"] == "split_up"


def test_every_row_names_a_known_group():
    assert {row[3] for row in KEYBOARD_SHORTCUTS} <= set(KEYBOARD_SHORTCUT_GROUPS)

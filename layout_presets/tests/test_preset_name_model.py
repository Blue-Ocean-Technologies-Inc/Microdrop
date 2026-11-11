# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the Save Current Layout dialog model."""

# Local imports.
from ..models.preset_name_model import PresetName

#: What the menus would report as already bound.
USED_SHORTCUTS = {"Ctrl+R": "Reset Layout", "Alt+1": "preset 'wide'"}


def _model(name, shortcut):
    return PresetName(name=name, shortcut=shortcut, used_shortcuts=USED_SHORTCUTS)


def test_collision_with_another_action_warns():
    model = _model("preset-2", "Ctrl+R")

    assert model.shortcut_warning == "Ctrl+R is already used by Reset Layout"


def test_collision_with_another_preset_warns():
    model = _model("tall", "Alt+1")

    assert model.shortcut_warning == "Alt+1 is already used by preset 'wide'"


def test_overwritten_preset_keeping_its_shortcut_does_not_warn():
    model = _model("  wide ", "Alt+1")

    assert model.shortcut_warning == ""


def test_free_or_empty_shortcut_does_not_warn():
    assert _model("tall", "Alt+2").shortcut_warning == ""
    assert _model("tall", "").shortcut_warning == ""


def test_warning_follows_the_shortcut():
    model = _model("tall", "Alt+2")
    model.shortcut = "Ctrl+R"

    assert model.shortcut_warning != ""
    assert model.is_name_valid

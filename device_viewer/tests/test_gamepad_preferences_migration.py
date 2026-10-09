# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the one-shot move of gamepad preferences to the plugin (#783)."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences

# Microdrop package imports.
from device_viewer.consts import (
    GAMEPAD_PLUGIN_PREFERENCES_PATH,
    GAMEPAD_PREFERENCES_MOVED_KEY,
    PREFERENCES_PATH,
)
from device_viewer.preferences import migrate_gamepad_preferences


@pytest.fixture
def preferences():
    return Preferences()


def _old(key):
    return f"{PREFERENCES_PATH}.{key}"


def _new(key):
    return f"{GAMEPAD_PLUGIN_PREFERENCES_PATH}.{key}"


def test_saved_bindings_move_to_the_plugin_node(preferences):
    preferences.set(_old("gamepad_btn_split"), "7")
    preferences.set(_old("gamepad_debounce_find"), "1.5")
    preferences.set(_old("gamepad_enabled"), "True")
    preferences.set(_old("ZOOM_SENSITIVITY"), "9")

    migrate_gamepad_preferences(preferences)

    assert GAMEPAD_PLUGIN_PREFERENCES_PATH == "microdrop.gamepad_controls"
    assert preferences.get(_new("gamepad_btn_split")) == "7"
    assert preferences.get(_new("gamepad_debounce_find")) == "1.5"
    assert preferences.get(_new("gamepad_enabled")) is None
    assert set(preferences.keys(PREFERENCES_PATH)) == {
        "ZOOM_SENSITIVITY",
        GAMEPAD_PREFERENCES_MOVED_KEY,
    }


def test_a_value_already_on_the_plugin_node_wins(preferences):
    preferences.set(_old("gamepad_btn_clear"), "4")
    preferences.set(_new("gamepad_btn_clear"), "6")

    migrate_gamepad_preferences(preferences)

    assert preferences.get(_new("gamepad_btn_clear")) == "6"
    assert preferences.get(_old("gamepad_btn_clear")) is None


def test_the_move_runs_once(preferences):
    preferences.set(_old("gamepad_btn_find"), "5")
    migrate_gamepad_preferences(preferences)
    preferences.set(_new("gamepad_btn_find"), "10")

    # An older Microdrop run in between writes its key back.
    preferences.set(_old("gamepad_btn_find"), "5")
    migrate_gamepad_preferences(preferences)

    assert preferences.get(_new("gamepad_btn_find")) == "10"


def test_a_fresh_install_only_records_the_marker(preferences):
    migrate_gamepad_preferences(preferences)

    assert preferences.keys(GAMEPAD_PLUGIN_PREFERENCES_PATH) == []
    assert preferences.get(_old(GAMEPAD_PREFERENCES_MOVED_KEY)) is not None


def test_the_move_is_saved_to_the_preferences_file(tmp_path):
    filename = str(tmp_path / "prefs.ini")
    preferences = Preferences(filename=filename)
    preferences.set(_old("gamepad_btn_split"), "7")
    preferences.set(_old("gamepad_enabled"), "True")

    migrate_gamepad_preferences(preferences)
    reloaded = Preferences(filename=filename)

    assert reloaded.get(_new("gamepad_btn_split")) == "7"
    assert reloaded.get(_old(GAMEPAD_PREFERENCES_MOVED_KEY)) is not None
    assert reloaded.get(_old("gamepad_btn_split")) is None
    assert reloaded.get(_old("gamepad_enabled")) is None


def test_a_failed_save_keeps_the_move_in_memory(preferences, monkeypatch):
    def fail_flush():
        raise OSError("preferences file is read-only")

    monkeypatch.setattr(preferences, "flush", fail_flush)
    preferences.set(_old("gamepad_btn_add"), "3")

    migrate_gamepad_preferences(preferences)

    assert preferences.get(_new("gamepad_btn_add")) == "3"
    assert preferences.get(_old("gamepad_btn_add")) is None

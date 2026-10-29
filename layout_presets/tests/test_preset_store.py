# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the layout-preset store and its naming rule."""

# Standard library imports.
import pickle

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.tasks.api import PaneItem, TaskLayout, TaskWindowLayout

# Local imports.
from ..consts import PRESET_FILE_SUFFIX, SHORTCUTS_FILENAME
from ..models.preset_store import PresetStore, is_valid_preset_name

#: Saved with the protocol envisage's TasksApplication uses by default.
PROTOCOL = 4


def _window_layout():
    return TaskWindowLayout(
        TaskLayout(
            id="microdrop_application.task",
            left=PaneItem("device_viewer.pane", width=300),
        ),
        active_task="microdrop_application.task",
        position=(10, 20),
        size=(1280, 800),
    )


def _touch_presets(directory, *names):
    for name in names:
        (directory / f"{name}{PRESET_FILE_SUFFIX}").write_bytes(
            pickle.dumps(_window_layout(), protocol=PROTOCOL)
        )


def test_first_default_name_in_an_empty_directory(tmp_path):
    store = PresetStore(directory=str(tmp_path / "missing"))

    assert store.next_default_name() == "preset-1"


def test_default_name_fills_the_first_gap(tmp_path):
    _touch_presets(tmp_path, "preset-1", "preset-3")
    store = PresetStore(directory=str(tmp_path))

    assert store.next_default_name() == "preset-2"


@pytest.mark.parametrize(
    "name",
    ["", "   ", "a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b"],
)
def test_unsafe_names_are_rejected(name):
    assert not is_valid_preset_name(name)


@pytest.mark.parametrize("name", ["preset-1", "Wide pane", "  padded  "])
def test_safe_names_are_accepted(name):
    assert is_valid_preset_name(name)


def test_save_strips_the_name(tmp_path):
    store = PresetStore(directory=str(tmp_path))
    store.save("  padded  ", _window_layout(), PROTOCOL)

    assert (tmp_path / f"padded{PRESET_FILE_SUFFIX}").is_file()
    assert store.presets == ["padded"]


def test_save_rejects_an_invalid_name(tmp_path):
    store = PresetStore(directory=str(tmp_path))

    with pytest.raises(ValueError):
        store.save("a/b", _window_layout(), PROTOCOL)

    assert list(tmp_path.iterdir()) == []


def test_save_and_load_round_trip(tmp_path):
    store = PresetStore(directory=str(tmp_path / "layout_presets"))
    store.save("wide", _window_layout(), PROTOCOL)

    layout = store.load("wide")

    assert isinstance(layout, TaskWindowLayout)
    assert layout.active_task == "microdrop_application.task"
    assert layout.size == (1280, 800)
    assert layout.position == (10, 20)

    task_layout = layout.items[0]

    assert isinstance(task_layout, TaskLayout)
    assert task_layout.id == "microdrop_application.task"
    assert task_layout.left.id == "device_viewer.pane"
    assert task_layout.left.width == 300


def test_save_overwrites_a_preset_of_the_same_name(tmp_path):
    store = PresetStore(directory=str(tmp_path))
    store.save("wide", _window_layout(), PROTOCOL)

    replacement = _window_layout()
    replacement.size = (800, 600)
    store.save("wide", replacement, PROTOCOL)

    assert store.load("wide").size == (800, 600)
    assert store.presets == ["wide"]


def test_refresh_lists_presets_sorted(tmp_path):
    _touch_presets(tmp_path, "zeta", "Alpha", "beta")
    (tmp_path / "notes.txt").write_text("not a preset")
    store = PresetStore(directory=str(tmp_path))

    store.refresh()

    assert store.presets == ["Alpha", "beta", "zeta"]


def test_unreadable_preset_is_skipped_and_logged(tmp_path, caplog):
    _touch_presets(tmp_path, "good")
    (tmp_path / f"broken{PRESET_FILE_SUFFIX}").write_bytes(b"not a pickle")
    store = PresetStore(directory=str(tmp_path))

    store.refresh()

    assert store.presets == ["good"]
    assert store.load("broken") is None
    assert any(
        record.exc_info is not None and "broken" in record.getMessage()
        for record in caplog.records
    )


def test_first_default_shortcut_in_an_empty_store(tmp_path):
    store = PresetStore(directory=str(tmp_path))

    assert store.next_default_shortcut() == "Alt+1"


def test_default_shortcut_fills_the_first_gap(tmp_path):
    store = PresetStore(directory=str(tmp_path))
    store.save("first", _window_layout(), PROTOCOL, shortcut="Alt+1")
    store.save("third", _window_layout(), PROTOCOL, shortcut="Alt+3")

    assert store.next_default_shortcut() == "Alt+2"


def test_default_shortcut_ends_with_zero_then_none(tmp_path):
    store = PresetStore(directory=str(tmp_path))

    for key in "123456789":
        store.save(f"p{key}", _window_layout(), PROTOCOL, shortcut=f"Alt+{key}")

    assert store.next_default_shortcut() == "Alt+0"

    store.save("p0", _window_layout(), PROTOCOL, shortcut="Alt+0")

    assert store.next_default_shortcut() == ""


def test_shortcut_persists_across_stores(tmp_path):
    PresetStore(directory=str(tmp_path)).save(
        "wide", _window_layout(), PROTOCOL, shortcut="Ctrl+Shift+1"
    )
    store = PresetStore(directory=str(tmp_path))

    store.refresh()

    assert store.shortcuts == {"wide": "Ctrl+Shift+1"}
    assert store.shortcut_for("wide") == "Ctrl+Shift+1"
    assert store.shortcut_for("missing") == ""


def test_overwrite_replaces_or_clears_the_shortcut(tmp_path):
    store = PresetStore(directory=str(tmp_path))
    store.save("wide", _window_layout(), PROTOCOL, shortcut="Alt+1")

    store.save("wide", _window_layout(), PROTOCOL, shortcut="Alt+2")

    assert store.shortcut_for("wide") == "Alt+2"

    store.save("wide", _window_layout(), PROTOCOL)

    assert store.shortcuts == {}


def test_refresh_drops_the_shortcut_of_a_deleted_preset(tmp_path):
    store = PresetStore(directory=str(tmp_path))
    store.save("wide", _window_layout(), PROTOCOL, shortcut="Alt+1")
    store.save("tall", _window_layout(), PROTOCOL, shortcut="Alt+2")

    (tmp_path / f"wide{PRESET_FILE_SUFFIX}").unlink()
    store.refresh()

    assert store.presets == ["tall"]
    assert store.shortcuts == {"tall": "Alt+2"}
    assert store.next_default_shortcut() == "Alt+1"


def test_damaged_shortcuts_file_keeps_the_presets(tmp_path, caplog):
    _touch_presets(tmp_path, "wide")
    (tmp_path / SHORTCUTS_FILENAME).write_text("{not json")
    store = PresetStore(directory=str(tmp_path))

    store.refresh()

    assert store.presets == ["wide"]
    assert store.shortcuts == {}
    assert any(record.exc_info is not None for record in caplog.records)

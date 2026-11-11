# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the Manage Layout Presets dialog model."""

# Enthought library imports.
from pyface.tasks.api import TaskWindowLayout

# Local imports.
from ..models.preset_store import PresetStore
from ..models.preset_table_model import PresetTable

#: What the menus would report outside the presets.
USED_SHORTCUTS = {"Ctrl+R": "Reset Layout"}


def _table(tmp_path, **shortcuts):
    store = PresetStore(directory=str(tmp_path))

    for name, shortcut in shortcuts.items():
        store.save(name, TaskWindowLayout(), 4, shortcut=shortcut)

    return PresetTable.from_store(store, USED_SHORTCUTS)


def _row(table, name):
    return next(row for row in table.rows if row.name == name)


def test_rows_mirror_the_store_without_self_collision(tmp_path):
    table = _table(tmp_path, wide="Alt+1", tall="")

    assert [(row.name, row.shortcut) for row in table.rows] == [
        ("tall", ""),
        ("wide", "Alt+1"),
    ]
    assert all(row.warning == "" for row in table.rows)


def test_two_rows_on_one_chord_warn_each_other(tmp_path):
    table = _table(tmp_path, wide="Alt+1", tall="Alt+2")

    _row(table, "tall").shortcut = "Alt+1"

    assert _row(table, "tall").warning == "Alt+1 is already used by preset 'wide'"
    assert _row(table, "wide").warning == "Alt+1 is already used by preset 'tall'"

    _row(table, "tall").shortcut = "Alt+3"

    assert _row(table, "wide").warning == ""


def test_collision_with_an_app_shortcut_warns(tmp_path):
    table = _table(tmp_path, wide="Alt+1")

    _row(table, "wide").shortcut = "Ctrl+R"

    assert _row(table, "wide").warning == "Ctrl+R is already used by Reset Layout"


def test_changes_after_editing_and_deleting(tmp_path):
    table = _table(tmp_path, wide="Alt+1", tall="Alt+2", square="")

    _row(table, "square").shortcut = "Alt+3"
    _row(table, "wide").shortcut = ""
    table.selected = _row(table, "tall")
    table.delete_selected()

    assert [row.name for row in table.rows] == ["square", "wide"]
    assert table.selected is None
    assert table.changes() == (["tall"], {}, {"square": "Alt+3", "wide": ""})


def test_deleting_a_row_clears_the_collision_it_caused(tmp_path):
    table = _table(tmp_path, wide="Alt+1", tall="Alt+1")

    assert _row(table, "wide").warning != ""

    table.selected = _row(table, "tall")
    table.delete_selected()

    assert _row(table, "wide").warning == ""


def test_invalid_rename_blocks_accept(tmp_path):
    table = _table(tmp_path, wide="Alt+1")
    row = _row(table, "wide")

    assert table.can_accept

    row.name = "wide/tall"

    assert row.name_error == "A preset name cannot contain /"
    assert row.warning == row.name_error
    assert not table.can_accept

    row.name = "  Wide room  "

    assert row.name_error == ""
    assert table.can_accept


def test_duplicate_row_name_warns_and_blocks_accept(tmp_path):
    table = _table(tmp_path, wide="Alt+1", tall="Alt+2")

    _row(table, "tall").name = "WIDE"

    assert _row(table, "WIDE").warning == "Another preset is already named 'WIDE'."
    assert not table.can_accept


def test_rename_onto_a_deleted_row_is_allowed(tmp_path):
    table = _table(tmp_path, wide="Alt+1", tall="Alt+2")
    _row(table, "tall").name = "wide"

    assert not table.can_accept

    table.selected = _row(table, "wide")
    table.delete_selected()

    assert table.can_accept


def test_rename_onto_an_unlisted_file_on_disk_is_refused(tmp_path):
    table = _table(tmp_path, wide="Alt+1")
    table.disk_names = table.disk_names + ["broken"]

    _row(table, "wide").name = "broken"

    assert not table.can_accept


def test_changes_with_a_rename_and_a_shortcut_edit_on_one_row(tmp_path):
    table = _table(tmp_path, wide="Alt+1", tall="Alt+2")
    row = _row(table, "wide")

    row.name = " wider "
    row.shortcut = "Alt+5"

    assert table.changes() == ([], {"wide": "wider"}, {"wider": "Alt+5"})


def test_deleting_a_renamed_row_deletes_its_saved_preset(tmp_path):
    table = _table(tmp_path, wide="Alt+1", tall="Alt+2")
    row = _row(table, "wide")
    row.name = "wider"

    table.selected = row
    table.delete_selected()

    assert table.changes() == (["wide"], {}, {})

"""Tests for bulk-set: RowManager.steps_under + BulkSetDialog (#474)."""

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column


@pytest.fixture
def manager():
    return RowManager(columns=[
        make_type_column(), make_id_column(),
        make_name_column(), make_duration_column(),
    ])


# --- RowManager.steps_under ---

def test_steps_under_single_step(manager):
    s = manager.add_step()
    assert manager.steps_under([s]) == [(0,)]


def test_steps_under_group_first_level_only(manager):
    g = manager.add_group()                 # (0,)
    manager.add_step(parent_path=g)         # (0, 0)
    sub = manager.add_group(parent_path=g)  # (0, 1)
    manager.add_step(parent_path=sub)       # (0, 1, 0)
    # Non-recursive: only the group's direct child steps, not the nested one.
    assert manager.steps_under([g]) == [(0, 0)]


def test_steps_under_group_recursive(manager):
    g = manager.add_group()                 # (0,)
    manager.add_step(parent_path=g)         # (0, 0)
    sub = manager.add_group(parent_path=g)  # (0, 1)
    manager.add_step(parent_path=sub)       # (0, 1, 0)
    assert manager.steps_under([g], recursive=True) == [(0, 0), (0, 1, 0)]


def test_steps_under_dedups_step_and_enclosing_group(manager):
    g = manager.add_group()                 # (0,)
    s = manager.add_step(parent_path=g)     # (0, 0)
    # The step is both directly selected and reached under its group — once.
    assert manager.steps_under([s, g]) == [(0, 0)]


def test_steps_under_empty_group(manager):
    g = manager.add_group()
    assert manager.steps_under([g]) == []


# --- BulkSetDialog ---

def test_dialog_lists_only_settable_columns(qapp, manager):
    from pluggable_protocol_tree.views.bulk_set_dialog import BulkSetDialog
    dialog = BulkSetDialog(manager)
    settable = set(dialog._rows)
    assert {"duration_s", "name"} <= settable
    assert "type" not in settable and "id" not in settable


def test_dialog_values_only_includes_ticked_columns(qapp, manager):
    from pluggable_protocol_tree.views.bulk_set_dialog import BulkSetDialog
    dialog = BulkSetDialog(manager)
    assert dialog.values() == {}
    apply_checkbox, _reader = dialog._rows["duration_s"]
    apply_checkbox.setChecked(True)
    # The editor was seeded with the template's default duration.
    assert dialog.values() == {"duration_s": manager.step_type().duration_s}


def test_dialog_apply_nested_flag(qapp, manager):
    from pluggable_protocol_tree.views.bulk_set_dialog import BulkSetDialog
    dialog = BulkSetDialog(manager)
    assert dialog.apply_nested is False
    dialog.nested_checkbox.setChecked(True)
    assert dialog.apply_nested is True

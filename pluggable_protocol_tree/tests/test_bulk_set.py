# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for bulk-set: RowManager.steps_under + BulkSetDialog (#474)."""

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.route_repetitions_column import (
    make_route_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager


@pytest.fixture
def manager():
    return RowManager(
        columns=[
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
        ]
    )


# --- RowManager.steps_under ---


def test_steps_under_single_step(manager):
    s = manager.add_step()
    assert manager.steps_under([s]) == [(0,)]


def test_steps_under_group_first_level_only(manager):
    g = manager.add_group()  # (0,)
    manager.add_step(parent_path=g)  # (0, 0)
    sub = manager.add_group(parent_path=g)  # (0, 1)
    manager.add_step(parent_path=sub)  # (0, 1, 0)
    # Non-recursive: only the group's direct child steps, not the nested one.
    assert manager.steps_under([g]) == [(0, 0)]


def test_steps_under_group_recursive(manager):
    g = manager.add_group()  # (0,)
    manager.add_step(parent_path=g)  # (0, 0)
    sub = manager.add_group(parent_path=g)  # (0, 1)
    manager.add_step(parent_path=sub)  # (0, 1, 0)
    assert manager.steps_under([g], recursive=True) == [(0, 0), (0, 1, 0)]


def test_steps_under_dedups_step_and_enclosing_group(manager):
    g = manager.add_group()  # (0,)
    s = manager.add_step(parent_path=g)  # (0, 0)
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


# --- RowManager.set_values through the column handlers ---


@pytest.fixture
def route_manager():
    return RowManager(
        columns=[
            make_name_column(),
            make_duration_column(),
            make_routes_column(),
            make_repeat_duration_column(),
            make_route_repetitions_column(),
        ]
    )


def _add_route_steps(manager, count, **values):
    return [
        manager.add_step(
            values={"routes": [["a", "b", "c", "a"]], "duration_s": 1.0, **values}
        )
        for _ in range(count)
    ]


def _record_cell_changes(manager):
    events = []
    manager.observe(lambda event: events.append(event.new), "cell_changed")

    return events


class _ConfirmCalls(list):
    """The prompts' kwargs, plus the answer every prompt returns."""

    answer = None


@pytest.fixture
def confirm_calls(monkeypatch):
    """Record handoff prompts; answer with ``confirm_calls.answer``."""
    import pluggable_protocol_tree.builtins.repeat_duration_column as mod

    calls = _ConfirmCalls()
    calls.answer = mod.YES

    def _confirm(*args, **kwargs):
        calls.append(kwargs)

        return calls.answer

    monkeypatch.setattr(mod, "confirm", _confirm)

    return calls


def test_bulk_route_reps_hands_duration_rows_back_to_count_mode(route_manager):
    paths = _add_route_steps(route_manager, 2)

    for path in paths:
        route_manager.get_row(path).repeat_duration_controls = True

    events = _record_cell_changes(route_manager)
    route_manager.set_values(paths, "route_repetitions", 4)

    for path in paths:
        row = route_manager.get_row(path)

        assert row.route_repetitions == 4
        assert row.repeat_duration_controls is False

    assert events == [
        {"path": tuple(path), "col_id": "route_repetitions"} for path in paths
    ]


def test_bulk_repeat_duration_prompts_once_for_the_batch(route_manager, confirm_calls):
    paths = _add_route_steps(route_manager, 3)
    events = _record_cell_changes(route_manager)
    route_manager.set_values(paths, "repeat_duration", 30.0)

    assert len(confirm_calls) == 1
    assert confirm_calls[0]["title"] == "Switch to Repeat Duration Control"
    assert "Apply to all 3 rows?" in confirm_calls[0]["message"]

    for path in paths:
        row = route_manager.get_row(path)

        assert row.repeat_duration == 30.0
        assert row.repeat_duration_controls is True

    assert len(events) == 3


def test_bulk_repeat_duration_cancel_writes_nothing(route_manager, confirm_calls):
    paths = _add_route_steps(route_manager, 2)
    confirm_calls.answer = None
    events = _record_cell_changes(route_manager)
    route_manager.set_values(paths, "repeat_duration", 30.0)

    for path in paths:
        row = route_manager.get_row(path)

        assert row.repeat_duration == 0.0
        assert row.repeat_duration_controls is False

    assert events == []


def test_bulk_repeat_duration_zero_hands_back_with_one_prompt(
    route_manager, confirm_calls
):
    paths = _add_route_steps(route_manager, 2, repeat_duration=30.0)

    for path in paths:
        route_manager.get_row(path).repeat_duration_controls = True

    route_manager.set_values(paths, "repeat_duration", 0.0)

    assert [call["title"] for call in confirm_calls] == ["Switch to Route Reps Control"]

    for path in paths:
        assert route_manager.get_row(path).repeat_duration_controls is False


def test_bulk_repeat_duration_in_duration_mode_is_a_plain_write(
    route_manager, confirm_calls
):
    paths = _add_route_steps(route_manager, 2, repeat_duration=30.0)

    for path in paths:
        route_manager.get_row(path).repeat_duration_controls = True

    route_manager.set_values(paths, "repeat_duration", 45.0)

    assert confirm_calls == []

    for path in paths:
        assert route_manager.get_row(path).repeat_duration == 45.0

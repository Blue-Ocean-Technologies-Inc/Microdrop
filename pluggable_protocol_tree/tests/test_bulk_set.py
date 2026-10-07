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

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QComboBox, QDoubleSpinBox
from traits.api import Bool, Float, List, Str

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
from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler,
    BaseCompoundColumnModel,
    CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import DoubleSpinBoxColumnView


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
    apply_checkbox, _value_widget, _reader = dialog._rows["duration_s"]
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


# --- Compound columns: a heater-temperature-shaped Bool + two Floats ---

SETPOINT_FIELDS = {
    "bulk_set_temp": "Set Temp",
    "bulk_target_c": "Target Temp (°C)",
    "bulk_tolerance_c": "Tolerance (°C)",
}


class _SetpointCompoundModel(BaseCompoundColumnModel):
    base_id = "bulk_setpoint"

    def field_specs(self):
        return [
            FieldSpec("bulk_set_temp", "Set Temp", False),
            FieldSpec("bulk_target_c", "Target Temp (°C)", 40.0),
            FieldSpec("bulk_tolerance_c", "Tolerance (°C)", 1.0),
        ]

    def trait_for_field(self, field_id):
        if field_id == "bulk_set_temp":
            return Bool(False)

        if field_id == "bulk_target_c":
            return Float(40.0)

        if field_id == "bulk_tolerance_c":
            return Float(1.0)

        raise KeyError(field_id)


class _GatedSetpointView(DoubleSpinBoxColumnView):
    """Read-only while the row's Set Temp is off — the cross-cell gate that
    made the default template hide the setpoint fields from Bulk Set."""

    depends_on_row_traits = List(Str, value=["bulk_set_temp"])

    def get_flags(self, row):
        flags = super().get_flags(row)

        if not getattr(row, "bulk_set_temp", False):
            flags &= ~Qt.ItemIsEditable

        return flags


class _SpyHandler(BaseCompoundColumnHandler):
    """Record every field edit routed to the compound handler."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def on_interact(self, row, model, field_id, value):
        self.calls.append((field_id, value))

        return super().on_interact(row, model, field_id, value)


@pytest.fixture
def setpoint_handler():
    return _SpyHandler()


@pytest.fixture
def setpoint_manager(setpoint_handler):
    compound = CompoundColumn(
        model=_SetpointCompoundModel(),
        view=DictCompoundColumnView(
            cell_views={
                "bulk_set_temp": CheckboxColumnView(),
                "bulk_target_c": _GatedSetpointView(
                    low=0.0, high=150.0, decimals=1, single_step=1.0
                ),
                "bulk_tolerance_c": _GatedSetpointView(
                    low=0.0, high=20.0, decimals=1, single_step=0.5
                ),
            }
        ),
        handler=setpoint_handler,
    )

    return RowManager(
        columns=[make_type_column(), make_name_column(), *_expand_compound(compound)]
    )


def _tick(dialog, col_id, value):
    """Tick ``col_id``'s Apply box and enter ``value`` in its editor."""
    apply_checkbox, value_widget, _reader = dialog._rows[col_id]
    apply_checkbox.setChecked(True)

    if isinstance(value_widget, QComboBox):
        value_widget.setCurrentIndex(int(value))
    else:
        value_widget.setValue(value)


def test_dialog_offers_every_compound_field(qapp, setpoint_manager):
    from pluggable_protocol_tree.views.bulk_set_dialog import BulkSetDialog

    dialog = BulkSetDialog(setpoint_manager)
    labels = {
        col_id: dialog._rows[col_id][0].text()
        for col_id in SETPOINT_FIELDS
        if col_id in dialog._rows
    }

    # The setpoints are gated off on the default template, yet still offered.
    assert labels == SETPOINT_FIELDS

    _apply, set_temp_widget, _reader = dialog._rows["bulk_set_temp"]

    # The Bool value is an Off/On choice, not a second checkbox beside Apply.
    assert isinstance(set_temp_widget, QComboBox)
    assert [set_temp_widget.itemText(i) for i in range(2)] == ["Off", "On"]
    assert set_temp_widget.currentIndex() == 0

    _apply, target_widget, _reader = dialog._rows["bulk_target_c"]

    assert isinstance(target_widget, QDoubleSpinBox)
    assert (target_widget.minimum(), target_widget.maximum()) == (0.0, 150.0)
    assert target_widget.decimals() == 1
    assert target_widget.value() == 40.0

    _apply, tolerance_widget, _reader = dialog._rows["bulk_tolerance_c"]

    assert isinstance(tolerance_widget, QDoubleSpinBox)
    assert tolerance_widget.maximum() == 20.0
    assert tolerance_widget.value() == 1.0


def test_bulk_apply_sets_each_compound_field(qapp, setpoint_manager, setpoint_handler):
    from pluggable_protocol_tree.views.bulk_set_dialog import BulkSetDialog

    paths = [setpoint_manager.add_step() for _ in range(2)]
    dialog = BulkSetDialog(setpoint_manager)
    _tick(dialog, "bulk_set_temp", True)
    _tick(dialog, "bulk_target_c", 55.5)
    _tick(dialog, "bulk_tolerance_c", 2.5)
    updates = dialog.values()

    assert updates == {
        "bulk_set_temp": True,
        "bulk_target_c": 55.5,
        "bulk_tolerance_c": 2.5,
    }

    events = _record_cell_changes(setpoint_manager)

    for col_id, value in updates.items():
        setpoint_manager.set_values(paths, col_id, value)

    for path in paths:
        row = setpoint_manager.get_row(path)

        assert row.bulk_set_temp is True
        assert row.bulk_target_c == 55.5
        assert row.bulk_tolerance_c == 2.5

    # Same route as a cell edit: the compound handler sees each field, and
    # every written cell is announced so the tree repaints it.
    assert setpoint_handler.calls == [
        (col_id, value) for col_id, value in updates.items() for _path in paths
    ]
    assert events == [
        {"path": tuple(path), "col_id": col_id} for col_id in updates for path in paths
    ]


def test_bulk_apply_float_field_leaves_the_bool_alone(qapp, setpoint_manager):
    from pluggable_protocol_tree.views.bulk_set_dialog import BulkSetDialog

    on_path = setpoint_manager.add_step(values={"bulk_set_temp": True})
    off_path = setpoint_manager.add_step()
    dialog = BulkSetDialog(setpoint_manager)
    _tick(dialog, "bulk_target_c", 60.0)
    updates = dialog.values()

    assert updates == {"bulk_target_c": 60.0}

    for col_id, value in updates.items():
        setpoint_manager.set_values([on_path, off_path], col_id, value)

    assert setpoint_manager.get_row(on_path).bulk_set_temp is True
    assert setpoint_manager.get_row(off_path).bulk_set_temp is False

    for path in (on_path, off_path):
        assert setpoint_manager.get_row(path).bulk_target_c == 60.0

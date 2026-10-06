# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the Fill Pattern logic: value generation, numeric field
discovery (incl. compound enabler checkboxes), applying to the tree, and
the dialog model's preview/validation."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import Qt

# Microdrop package imports.
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import STEP_PATTERN_ALTERNATE, STEP_PATTERN_RAMP
from pluggable_protocol_tree.demos.enabled_count_compound import (
    make_enabled_count_compound,
)
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.models.step_pattern_model import StepPatternModel
from pluggable_protocol_tree.services.step_pattern import (
    PatternField,
    alternate_values,
    apply_pattern_to_steps,
    default_group_name,
    discover_pattern_fields,
    fit_increment,
    fit_ramp_values,
    insert_pattern_steps,
    parse_values,
    ramp_values,
    selected_steps_in_order,
)
from pluggable_protocol_tree.services.step_pattern_controller import (
    StepPatternController,
)


def _is_editable(column, row):
    return bool(column.view.get_flags(row) & Qt.ItemIsEditable)


@pytest.fixture
def manager():
    return RowManager(
        columns=[
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
            make_repetitions_column(),
            *_expand_compound(make_enabled_count_compound()),
        ]
    )


def _fields_by_id(manager):
    fields = discover_pattern_fields(manager.columns, manager.step_type, _is_editable)

    return {field.col_id: field for field in fields}


# --- value generation ---


def test_ramp_even_division():
    assert ramp_values(50, 56, 2) == [50, 52, 54, 56]


def test_ramp_uneven_division_clamps_last_step_to_stop():
    assert ramp_values(50, 55, 2) == [50, 52, 54, 55]


def test_ramp_descending():
    assert ramp_values(120, 114, 2) == [120, 118, 116, 114]


def test_ramp_float_increment_lands_on_stop():
    assert ramp_values(0.0, 0.3, 0.1) == [0.0, 0.1, 0.2, 0.3]


def test_ramp_rejects_non_positive_increment():
    with pytest.raises(ValueError):
        ramp_values(0, 10, 0)


def test_fit_ramp_spreads_over_count():
    assert fit_increment(50, 120, 5) == 17.5
    assert fit_ramp_values(50, 120, 5) == [50, 67.5, 85, 102.5, 120]


def test_alternate_cycles_pattern():
    assert alternate_values([50, 80], 5) == [50, 80, 50, 80, 50]


def test_parse_values_accepts_commas_and_spaces():
    assert parse_values("50, 80 95.5") == [50.0, 80.0, 95.5]


def test_parse_values_names_bad_entry():
    with pytest.raises(ValueError, match="'abc'"):
        parse_values("50, abc")


# --- field discovery ---


def test_discovers_numeric_columns_only(manager):
    fields = _fields_by_id(manager)

    assert set(fields) == {"duration_s", "repetitions", "ec_count"}
    assert fields["duration_s"].label == "Duration (s)"
    assert not fields["duration_s"].is_int
    assert fields["repetitions"].is_int


def test_discovery_reads_view_bounds(manager):
    duration = _fields_by_id(manager)["duration_s"]

    assert (duration.low, duration.high) == (0.0, 10000.0)


def test_compound_field_records_enabler_checkbox(manager):
    fields = _fields_by_id(manager)

    assert fields["ec_count"].enabler_ids == ["ec_enabled"]
    assert fields["duration_s"].enabler_ids == []


# --- applying ---


def test_fit_writes_values_and_ticks_enabler(manager):
    paths = [manager.add_step() for _ in range(3)]
    field = _fields_by_id(manager)["ec_count"]

    apply_pattern_to_steps(manager, paths, field, [1, 2, 3])

    rows = [manager.get_row(p) for p in paths]
    assert [row.ec_count for row in rows] == [1, 2, 3]
    assert all(row.ec_enabled for row in rows)


def test_selected_steps_are_in_tree_order(manager):
    paths = [manager.add_step() for _ in range(3)]
    manager.select([paths[2], paths[0]])

    assert selected_steps_in_order(manager) == [paths[0], paths[2]]


def test_create_inserts_copies_after_anchor(manager):
    anchor = manager.add_step(values={"name": "Anchor", "repetitions": 4})
    manager.add_step(values={"name": "Tail"})
    field = _fields_by_id(manager)["duration_s"]

    new_paths = insert_pattern_steps(manager, anchor, field, [5.0, 6.0])

    assert new_paths == [(1,), (2,)]
    names = [row.name for row in manager.root.children]
    assert names == ["Anchor", "Anchor", "Anchor", "Tail"]
    assert manager.get_row((2,)).duration_s == 6.0
    assert manager.get_row((2,)).repetitions == 4
    assert manager.get_row((2,)).uuid != manager.get_row(anchor).uuid


def test_create_without_anchor_appends_copies_of_last_step(manager):
    manager.add_step(values={"name": "Last"})
    field = _fields_by_id(manager)["ec_count"]

    new_paths = insert_pattern_steps(manager, None, field, [7])

    row = manager.get_row(new_paths[0])
    assert new_paths == [(1,)]
    assert (row.name, row.ec_count, row.ec_enabled) == ("Last", 7, True)


# --- dialog model ---


def _model(**traits):
    fields = [
        PatternField(col_id="temp", label="Temp (°C)", low=20, high=120),
        PatternField(col_id="volts", label="Voltage (V)", is_int=True, high=150),
    ]

    return StepPatternModel(fields=fields, **traits)


def test_model_create_ramp_summary():
    model = _model(start=50, stop=120, increment=2)

    assert model.is_valid
    assert len(model.values) == 36
    assert model.summary.startswith("Will create 36 steps")


def test_model_fit_prefills_from_selection_and_reports_increment():
    model = _model(
        current_values={"temp": [50.0, 60.0, 70.0, 80.0, 120.0]}, fit_count=5
    )

    assert (model.start, model.stop) == (50.0, 120.0)
    assert model.values == [50, 67.5, 85, 102.5, 120]
    assert "Will set 5 selected steps, increment 17.5" in model.summary


def test_model_int_field_rounds_values():
    model = _model(field_label="Voltage (V)", start=100, stop=101, increment=0.4)

    assert model.values == [100, 100, 101, 101]


def test_model_refuses_out_of_bounds():
    model = _model(start=50, stop=130, increment=10)

    assert not model.is_valid
    assert "outside" in model.summary


def test_model_refuses_equal_ramp_ends():
    model = _model(start=50, stop=50)

    assert not model.is_valid


def test_model_alternate_create_count():
    model = _model(mode=STEP_PATTERN_ALTERNATE, alternate_text="50, 80", create_count=3)

    assert model.values == [50, 80, 50]
    assert model.is_valid


def test_model_alternate_requires_values():
    model = _model(mode=STEP_PATTERN_ALTERNATE, alternate_text=" ")

    assert not model.is_valid


# --- create in a new group ---


def test_create_in_group_places_group_after_anchor(manager):
    anchor = manager.add_step(values={"name": "Anchor"})
    manager.add_step(values={"name": "Tail"})
    field = _fields_by_id(manager)["duration_s"]

    new_paths = insert_pattern_steps(
        manager, anchor, field, [5.0, 6.0, 7.0], group_name="Duration ramp"
    )

    group = manager.get_row((1,))
    assert isinstance(group, GroupRow)
    assert group.name == "Duration ramp"
    assert new_paths == [(1, 0), (1, 1), (1, 2)]
    assert [row.duration_s for row in group.children] == [5.0, 6.0, 7.0]
    assert [row.name for row in manager.root.children] == [
        "Anchor",
        "Duration ramp",
        "Tail",
    ]


def test_create_in_group_without_anchor_appends_group(manager):
    manager.add_step()
    field = _fields_by_id(manager)["repetitions"]

    new_paths = insert_pattern_steps(manager, None, field, [2, 3], group_name="Reps")

    assert new_paths == [(1, 0), (1, 1)]
    assert manager.get_row((1,)).name == "Reps"


def test_default_group_name_strips_units_and_follows_mode():
    assert default_group_name("Target Temp (°C)", STEP_PATTERN_RAMP) == (
        "Target Temp ramp"
    )
    assert default_group_name("Voltage (V) [volts]", STEP_PATTERN_ALTERNATE) == (
        "Voltage pattern"
    )


def test_model_ticking_group_suggests_name_that_follows_mode():
    model = _model(start=50, stop=120, increment=2)
    model.create_in_group = True

    assert model.group_name == "Temp ramp"

    model.mode = STEP_PATTERN_ALTERNATE

    assert model.group_name == "Temp pattern"


def test_model_keeps_user_group_name():
    model = _model(start=50, stop=120, increment=2, create_in_group=True)
    model.group_name = "Heat up"
    model.mode = STEP_PATTERN_ALTERNATE

    assert model.group_name == "Heat up"


def test_model_group_summary():
    model = _model(start=50, stop=120, increment=2, create_in_group=True)

    assert model.summary.startswith("Will create 36 steps in group 'Temp ramp'")


def test_model_blank_group_name_is_invalid():
    model = _model(start=50, stop=120, increment=2, create_in_group=True)
    model.group_name = "  "

    assert not model.is_valid
    assert "group" in model.summary


def test_fit_mode_ignores_group_option(manager):
    paths = [manager.add_step() for _ in range(3)]
    manager.select(paths)
    field = _fields_by_id(manager)["duration_s"]
    model = StepPatternModel(
        fields=[field],
        fit_count=3,
        start=1,
        stop=3,
        create_in_group=True,
        group_name="",
    )

    assert model.is_valid
    assert model.new_group_name == ""
    assert "group" not in model.summary

    StepPatternController(manager=manager)._apply(model, paths)

    assert len(manager.root.children) == 3
    assert [manager.get_row(p).duration_s for p in paths] == [1.0, 2.0, 3.0]

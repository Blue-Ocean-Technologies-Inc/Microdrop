"""Tests for the force column — model, factory, view dependency
declarations. Reactive Qt-model wiring lives in Task 5."""

import pytest
from traits.api import HasTraits, Int

from pluggable_protocol_tree.models.column import Column

from dropbot_protocol_controls.protocol_columns.force_column import (
    ForceColumnModel,
    ForceColumnView,
    make_force_column,
)
from dropbot_protocol_controls.services.calibration_cache import cache
from dropbot_protocol_controls.services.force_math import force_for_step


@pytest.fixture(autouse=True)
def _reset_cache():
    cache.trait_set(
        liquid_capacitance_over_area=0.0,
        filler_capacitance_over_area=0.0,
    )
    yield
    cache.trait_set(
        liquid_capacitance_over_area=0.0,
        filler_capacitance_over_area=0.0,
    )


class _FakeRow(HasTraits):
    voltage = Int(100)


def test_make_force_column_returns_column_with_force_id():
    col = make_force_column()
    assert isinstance(col, Column)
    assert col.model.col_id == "force"
    assert col.model.col_name == "Force (mN/m)"
    assert col.view is not None
    assert col.handler is not None


def test_get_value_happy_path_matches_force_for_step():
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    expected_c_per_a = cache.capacitance_per_unit_area()
    assert expected_c_per_a is not None  # sanity

    model = ForceColumnModel(
        col_id="force", col_name="Force (mN/m)", default_value=0.0,
    )
    row = _FakeRow(voltage=100)

    expected = force_for_step(100.0, expected_c_per_a)
    assert expected is not None
    assert model.get_value(row) == pytest.approx(expected)


def test_get_value_no_calibration_returns_none():
    # Cache left at defaults (0.0 / 0.0) by the autouse fixture.
    model = ForceColumnModel(
        col_id="force", col_name="Force (mN/m)", default_value=0.0,
    )
    row = _FakeRow(voltage=100)
    assert model.get_value(row) is None


def test_get_value_voltage_zero_returns_none():
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    model = ForceColumnModel(
        col_id="force", col_name="Force (mN/m)", default_value=0.0,
    )
    row = _FakeRow(voltage=0)
    assert model.get_value(row) is None


def test_format_display_with_value_renders_two_decimals():
    view = ForceColumnView()
    row = _FakeRow(voltage=100)
    assert view.format_display(5.4321, row) == "5.43"


def test_format_display_with_none_returns_empty_string():
    view = ForceColumnView()
    row = _FakeRow(voltage=100)
    assert view.format_display(None, row) == ""


def test_view_class_attributes_are_set():
    view = ForceColumnView()
    assert view.renders_on_group is False
    assert view.hidden_by_default is False


def test_serialize_and_deserialize_are_identity_none():
    model = ForceColumnModel(
        col_id="force", col_name="Force (mN/m)", default_value=0.0,
    )
    assert model.serialize(123.4) is None
    assert model.deserialize("anything") is None
    assert model.serialize(None) is None
    assert model.deserialize(None) is None


def test_view_dependency_declarations_are_present():
    view = ForceColumnView()
    assert list(view.depends_on_row_traits) == ["voltage"]
    assert view.depends_on_event_source is cache
    assert view.depends_on_event_trait_name == "cache_changed"

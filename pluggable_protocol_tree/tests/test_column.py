"""Tests for BaseColumnModel, BaseColumnHandler, Column composite."""

from traits.api import Float, Str

from pluggable_protocol_tree.models.row import BaseRow, build_row_type
from pluggable_protocol_tree.models.column import (
    BaseColumnModel, BaseColumnHandler, Column,
)


def test_base_column_model_stores_metadata():
    m = BaseColumnModel(col_id="voltage", col_name="Voltage", default_value=100.0)
    assert m.col_id == "voltage"
    assert m.col_name == "Voltage"
    assert m.default_value == 100.0


def test_base_column_model_trait_for_row_returns_any_by_default():
    """Base model uses Any trait; typed variants override."""
    m = BaseColumnModel(col_id="x", col_name="X", default_value="hello")
    trait = m.trait_for_row()
    # Trait descriptor should accept the declared default when used
    RowType = build_row_type([_fake_col(m, trait)], base=BaseRow)
    r = RowType()
    assert r.x == "hello"


def _fake_col(model, trait):
    """Test helper — mimics what Column does for build_row_type."""
    class _C:
        pass
    c = _C()
    c.model = model
    c.model.trait_for_row = lambda: trait
    return c


def test_base_column_model_get_set_value_on_row():
    m = BaseColumnModel(col_id="voltage", col_name="Voltage", default_value=100.0)
    RowType = build_row_type([_fake_col(m, Float(100.0))], base=BaseRow)
    r = RowType()
    assert m.get_value(r) == 100.0
    assert m.set_value(r, 150.0) is True
    assert m.get_value(r) == 150.0


def test_base_column_model_serialize_deserialize_identity():
    """Default serialize/deserialize are identity for JSON-native types."""
    m = BaseColumnModel(col_id="x", col_name="X", default_value=0)
    assert m.serialize(42) == 42
    assert m.deserialize(42) == 42
    assert m.serialize("hello") == "hello"
    assert m.deserialize(True) is True


def test_base_column_handler_defaults():
    h = BaseColumnHandler()
    assert h.priority == 50
    assert h.wait_for_topics == []


def test_base_column_handler_on_interact_delegates_to_model():
    m = BaseColumnModel(col_id="voltage", col_name="Voltage", default_value=0.0)
    RowType = build_row_type([_fake_col(m, Float(0.0))], base=BaseRow)
    r = RowType()
    h = BaseColumnHandler()
    assert h.on_interact(r, m, 42.0) is True
    assert m.get_value(r) == 42.0


def test_column_composite_auto_wires_model_into_view_and_handler():
    """Column.traits_init should set view.model and handler.{model,view}."""
    from pluggable_protocol_tree.views.columns.base import BaseColumnView
    m = BaseColumnModel(col_id="x", col_name="X", default_value=0)
    v = BaseColumnView()
    h = BaseColumnHandler()
    col = Column(model=m, view=v, handler=h)
    assert col.view.model is m
    assert col.handler.model is m
    assert col.handler.view is v


def test_column_composite_creates_default_handler_if_none_given():
    from pluggable_protocol_tree.views.columns.base import BaseColumnView
    m = BaseColumnModel(col_id="x", col_name="X", default_value=0)
    v = BaseColumnView()
    col = Column(model=m, view=v)
    assert isinstance(col.handler, BaseColumnHandler)

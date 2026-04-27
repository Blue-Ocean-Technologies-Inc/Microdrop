"""Tests for the compound column base classes + CompoundColumn composite."""

import pytest
from traits.api import Bool, HasTraits, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel,
    BaseCompoundColumnView, CompoundColumn, DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class _DemoModel(BaseCompoundColumnModel):
    base_id = "demo"
    def field_specs(self):
        return [
            FieldSpec("ec_enabled", "Enabled", False),
            FieldSpec("ec_count",   "Count",   0),
        ]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


def test_base_model_serialize_deserialize_identity():
    m = _DemoModel()
    assert m.serialize("ec_enabled", True) is True
    assert m.deserialize("ec_count", 42) == 42


def test_base_model_get_set_value_via_attribute():
    m = _DemoModel()
    class Row(HasTraits):
        ec_enabled = Bool(False)
    r = Row()
    assert m.get_value(r, "ec_enabled") is False
    assert m.set_value(r, "ec_enabled", True) is True
    assert r.ec_enabled is True


def test_base_handler_on_interact_writes_through_to_model():
    m = _DemoModel()
    h = BaseCompoundColumnHandler()
    h.model = m
    class Row(HasTraits):
        ec_count = Int(0)
    r = Row()
    h.on_interact(r, m, "ec_count", 7)
    assert r.ec_count == 7


def test_dict_compound_column_view_lookup():
    cb = CheckboxColumnView()
    sb = IntSpinBoxColumnView(low=0, high=999)
    v = DictCompoundColumnView(cell_views={
        "ec_enabled": cb,
        "ec_count": sb,
    })
    assert v.cell_view_for_field("ec_enabled") is cb
    assert v.cell_view_for_field("ec_count") is sb


def test_dict_compound_column_view_unknown_field_raises():
    v = DictCompoundColumnView(cell_views={})
    with pytest.raises(KeyError):
        v.cell_view_for_field("missing")


def test_compound_column_traits_init_wires_handler_model():
    """CompoundColumn.traits_init injects the model into the handler."""
    m = _DemoModel()
    v = DictCompoundColumnView(cell_views={
        "ec_enabled": CheckboxColumnView(),
        "ec_count": IntSpinBoxColumnView(low=0, high=999),
    })
    h = BaseCompoundColumnHandler()
    cc = CompoundColumn(model=m, view=v, handler=h)
    assert cc.handler.model is m


def test_compound_column_default_handler_when_none_provided():
    """If handler is omitted, traits_init substitutes BaseCompoundColumnHandler."""
    m = _DemoModel()
    v = DictCompoundColumnView(cell_views={
        "ec_enabled": CheckboxColumnView(),
        "ec_count": IntSpinBoxColumnView(low=0, high=999),
    })
    cc = CompoundColumn(model=m, view=v)
    assert isinstance(cc.handler, BaseCompoundColumnHandler)
    assert cc.handler.model is m


def test_compound_column_rewires_model_on_handler_reassignment():
    """I2 regression: reassigning .handler after construction should
    re-wire handler.model so third-party authors don't have to remember."""
    m = _DemoModel()
    v = DictCompoundColumnView(cell_views={
        "ec_enabled": CheckboxColumnView(),
        "ec_count": IntSpinBoxColumnView(low=0, high=999),
    })
    cc = CompoundColumn(model=m, view=v)
    new_handler = BaseCompoundColumnHandler()
    cc.handler = new_handler
    assert new_handler.model is m

"""Tests for the synthetic demo enabled+count compound column."""

from pyface.qt.QtCore import Qt
from traits.api import Bool, HasTraits, Int

from pluggable_protocol_tree.demos.enabled_count_compound import (
    CountCellView, EnabledCountCompoundModel, make_enabled_count_compound,
)
from pluggable_protocol_tree.models.compound_column import (
    CompoundColumn, DictCompoundColumnView,
)


def test_factory_returns_compound_column_with_two_fields():
    cc = make_enabled_count_compound()
    assert isinstance(cc, CompoundColumn)
    specs = cc.model.field_specs()
    assert [s.field_id for s in specs] == ["ec_enabled", "ec_count"]
    assert [s.col_name for s in specs] == ["Enabled", "Count"]
    assert [s.default_value for s in specs] == [False, 0]


def test_model_traits_are_bool_and_int():
    m = EnabledCountCompoundModel()
    enabled_trait = m.trait_for_field("ec_enabled")
    count_trait = m.trait_for_field("ec_count")
    class Row(HasTraits):
        ec_enabled = enabled_trait
        ec_count = count_trait
    r = Row()
    assert r.ec_enabled is False
    assert r.ec_count == 0
    r.ec_enabled = True
    r.ec_count = 99
    assert r.ec_enabled is True
    assert r.ec_count == 99


def test_count_cell_view_read_only_when_enabled_false():
    v = CountCellView(low=0, high=999)
    class Row(HasTraits):
        ec_enabled = Bool(False)
        ec_count = Int(0)
    r = Row()
    flags = v.get_flags(r)
    assert not (flags & Qt.ItemIsEditable)


def test_count_cell_view_editable_when_enabled_true():
    v = CountCellView(low=0, high=999)
    class Row(HasTraits):
        ec_enabled = Bool(True)
        ec_count = Int(0)
    r = Row()
    flags = v.get_flags(r)
    assert flags & Qt.ItemIsEditable

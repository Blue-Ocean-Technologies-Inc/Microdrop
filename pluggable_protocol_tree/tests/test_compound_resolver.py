"""Tests for resolve_columns handling of compound entries."""

import pytest
from traits.api import Bool, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models._compound_adapters import _CompoundFieldAdapter
from pluggable_protocol_tree.session import resolve_columns
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


# Module-level so the resolver's importlib + dir() walk can find both
# the model class AND the make_*_compound factory.

class _RTestModel(BaseCompoundColumnModel):
    base_id = "rtest"
    def field_specs(self):
        return [FieldSpec("rt_a", "A", False),
                FieldSpec("rt_b", "B", 0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "rt_a" else Int(0)


def make_rtest_compound():
    return CompoundColumn(
        model=_RTestModel(),
        view=DictCompoundColumnView(cell_views={
            "rt_a": CheckboxColumnView(),
            "rt_b": IntSpinBoxColumnView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )


def test_resolve_compound_returns_n_synthesized_columns():
    """Two compound-field entries in the payload resolve to N flat
    Column instances (after expansion) — same shape as if they had
    been assembled live."""
    payload = {
        "columns": [
            {"id": "rt_a",
             "cls": f"{__name__}._RTestModel",
             "compound_id": "rtest",
             "compound_field_id": "rt_a"},
            {"id": "rt_b",
             "cls": f"{__name__}._RTestModel",
             "compound_id": "rtest",
             "compound_field_id": "rt_b"},
        ],
    }
    cols = resolve_columns(payload)
    assert len(cols) == 2
    assert all(isinstance(c.model, _CompoundFieldAdapter) for c in cols)
    assert [c.model.col_id for c in cols] == ["rt_a", "rt_b"]


def test_resolve_compound_calls_factory_once_per_compound():
    """Multiple field entries for the same compound must share the
    underlying compound model + handler instance — proves the factory
    was called once, not N times."""
    payload = {
        "columns": [
            {"id": "rt_a", "cls": f"{__name__}._RTestModel",
             "compound_id": "rtest", "compound_field_id": "rt_a"},
            {"id": "rt_b", "cls": f"{__name__}._RTestModel",
             "compound_id": "rtest", "compound_field_id": "rt_b"},
        ],
    }
    cols = resolve_columns(payload)
    assert cols[0].model.compound_model is cols[1].model.compound_model


def test_resolve_simple_columns_unchanged():
    """Regression: a payload with only simple columns resolves the
    same way as before PPT-11."""
    from pluggable_protocol_tree.builtins.repetitions_column import (
        RepetitionsColumnModel,
    )
    payload = {
        "columns": [
            {"id": "repetitions",
             "cls": "pluggable_protocol_tree.builtins.repetitions_column.RepetitionsColumnModel"},
        ],
    }
    cols = resolve_columns(payload)
    assert len(cols) == 1
    assert cols[0].model.col_id == "repetitions"

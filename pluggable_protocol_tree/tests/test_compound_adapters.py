"""Tests for the compound→single-cell adapter shims used by _assemble_columns."""

from unittest.mock import MagicMock

from traits.api import Bool, HasTraits, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models._compound_adapters import (
    _CompoundFieldAdapter, _CompoundFieldHandlerAdapter,
)
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel,
)


class _DemoModel(BaseCompoundColumnModel):
    base_id = "demo"
    def field_specs(self):
        return [FieldSpec("ec_enabled", "Enabled", False),
                FieldSpec("ec_count",   "Count",   0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


def test_field_adapter_proxies_to_compound_model():
    m = _DemoModel()
    a = _CompoundFieldAdapter(
        col_id="ec_count", col_name="Count", default_value=0,
        compound_model=m, field_id="ec_count",
        compound_base_id="demo", is_owner=False,
    )
    class Row(HasTraits):
        ec_count = Int(5)
    r = Row()
    assert a.get_value(r) == 5
    a.set_value(r, 9)
    assert r.ec_count == 9
    assert a.serialize(7) == 7
    assert a.deserialize(7) == 7


def test_field_adapter_trait_for_row_proxies_to_compound_model():
    m = _DemoModel()
    a = _CompoundFieldAdapter(
        col_id="ec_enabled", col_name="Enabled", default_value=False,
        compound_model=m, field_id="ec_enabled",
        compound_base_id="demo", is_owner=True,
    )
    trait = a.trait_for_row()
    # Trait should be the same shape as compound_model.trait_for_field returns:
    class Row(HasTraits):
        ec_enabled = trait
    r = Row()
    assert r.ec_enabled is False


def test_handler_adapter_on_interact_calls_compound_with_field_id():
    """Single-cell on_interact(row, model, value) translates to
    compound on_interact(row, compound_model, field_id, value)."""
    m = _DemoModel()
    h = MagicMock(spec=BaseCompoundColumnHandler)
    h.on_interact.return_value = True
    a = _CompoundFieldHandlerAdapter(
        compound_handler=h, compound_model=m, field_id="ec_count",
        is_owner=False, priority=20, wait_for_topics=[],
    )
    class Row(HasTraits):
        ec_count = Int(0)
    r = Row()
    result = a.on_interact(r, None, 11)   # second arg ignored by the adapter
    h.on_interact.assert_called_once_with(r, m, "ec_count", 11)
    assert result is True


def test_handler_adapter_owner_field_fires_on_step_once():
    m = _DemoModel()
    h = MagicMock(spec=BaseCompoundColumnHandler)
    owner = _CompoundFieldHandlerAdapter(
        compound_handler=h, compound_model=m, field_id="ec_enabled",
        is_owner=True, priority=20, wait_for_topics=[],
    )
    follower = _CompoundFieldHandlerAdapter(
        compound_handler=h, compound_model=m, field_id="ec_count",
        is_owner=False, priority=20, wait_for_topics=[],
    )
    row = object()
    ctx = object()
    owner.on_step(row, ctx)
    follower.on_step(row, ctx)
    h.on_step.assert_called_once_with(row, ctx)


def test_handler_adapter_mirrors_priority_and_wait_for_topics():
    """Adapter must report the compound's priority + wait_for_topics
    (used by _assemble_columns aggregation for executor subscriptions)."""
    m = _DemoModel()
    h = BaseCompoundColumnHandler()
    h.priority = 35
    h.wait_for_topics = ["t/applied"]
    a = _CompoundFieldHandlerAdapter(
        compound_handler=h, compound_model=m, field_id="ec_count",
        is_owner=False, priority=35, wait_for_topics=["t/applied"],
    )
    assert a.priority == 35
    assert a.wait_for_topics == ["t/applied"]

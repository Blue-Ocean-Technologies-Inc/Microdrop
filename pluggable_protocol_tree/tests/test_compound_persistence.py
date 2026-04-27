"""Tests for compound column persistence (serialize discriminators)."""

from traits.api import Bool, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.services.persistence import serialize_tree
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class _DemoModel(BaseCompoundColumnModel):
    base_id = "demo"
    def field_specs(self):
        return [FieldSpec("ec_enabled", "Enabled", False),
                FieldSpec("ec_count",   "Count",   0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


def _expand():
    cc = CompoundColumn(
        model=_DemoModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   IntSpinBoxColumnView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )
    return _expand_compound(cc)


def test_serialize_compound_field_entries_have_discriminators():
    """Each compound-field column entry has compound_id +
    compound_field_id; cls points at the compound MODEL class (not
    the adapter)."""
    cols = _expand()
    root = GroupRow(name="Root")
    payload = serialize_tree(root, cols)

    by_id = {e["id"]: e for e in payload["columns"]}
    assert "ec_enabled" in by_id
    assert "ec_count" in by_id

    enabled_entry = by_id["ec_enabled"]
    assert enabled_entry["compound_id"] == "demo"
    assert enabled_entry["compound_field_id"] == "ec_enabled"
    # cls qualname points at the compound model class, NOT the adapter:
    assert "_CompoundFieldAdapter" not in enabled_entry["cls"]
    assert "_DemoModel" in enabled_entry["cls"]


def test_serialize_simple_column_entries_have_no_discriminators():
    """Regression: single-cell columns continue to omit compound_id."""
    from pluggable_protocol_tree.builtins.repetitions_column import (
        make_repetitions_column,
    )
    root = GroupRow(name="Root")
    payload = serialize_tree(root, [make_repetitions_column()])
    entry = payload["columns"][0]
    assert "compound_id" not in entry
    assert "compound_field_id" not in entry


def test_serialize_compound_field_order_preserved():
    """Compound fields must appear in field_specs declaration order
    in the columns list (so the resolver's grouping pass works)."""
    cols = _expand()
    root = GroupRow(name="Root")
    payload = serialize_tree(root, cols)
    ids = [e["id"] for e in payload["columns"]]
    assert ids.index("ec_enabled") < ids.index("ec_count")

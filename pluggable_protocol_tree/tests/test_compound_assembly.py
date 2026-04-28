"""Tests for _assemble_columns expansion of compound contributions."""

from traits.api import Bool, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models._compound_adapters import (
    _CompoundFieldAdapter, _CompoundFieldHandlerAdapter,
)
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class _TwoFieldModel(BaseCompoundColumnModel):
    base_id = "two_field"
    def field_specs(self):
        return [FieldSpec("ec_enabled", "Enabled", False),
                FieldSpec("ec_count",   "Count",   0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


def _make_compound():
    return CompoundColumn(
        model=_TwoFieldModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   IntSpinBoxColumnView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )


def test_assemble_expands_compound_into_n_columns():
    """A two-field CompoundColumn contribution yields exactly 2 entries
    in _assemble_columns output, with col_id == field_id for each."""
    p = PluggableProtocolTreePlugin()
    p.contributed_columns = [_make_compound()]
    cols = p._assemble_columns()
    ids = [c.model.col_id for c in cols]
    assert "ec_enabled" in ids
    assert "ec_count" in ids
    assert ids.index("ec_enabled") + 1 == ids.index("ec_count"), (
        "compound fields must be adjacent in declaration order"
    )


def test_assemble_compound_columns_share_compound_model_and_handler():
    """All synthesized columns from one compound must share the same
    underlying compound model + handler instances (so on_step sees all
    fields and prefs round-trips work)."""
    p = PluggableProtocolTreePlugin()
    cc = _make_compound()
    p.contributed_columns = [cc]
    cols = [c for c in p._assemble_columns()
            if isinstance(c.model, _CompoundFieldAdapter)]
    assert len(cols) == 2
    assert cols[0].model.compound_model is cc.model
    assert cols[1].model.compound_model is cc.model
    assert cols[0].handler.compound_handler is cc.handler
    assert cols[1].handler.compound_handler is cc.handler


def test_assemble_first_compound_field_is_owner_others_are_not():
    """Only the first field's handler adapter has is_owner=True;
    follower fields are is_owner=False (so on_step fires once per row)."""
    p = PluggableProtocolTreePlugin()
    p.contributed_columns = [_make_compound()]
    adapters = [c.handler for c in p._assemble_columns()
                if isinstance(c.handler, _CompoundFieldHandlerAdapter)]
    assert adapters[0].is_owner is True
    assert all(a.is_owner is False for a in adapters[1:])


def test_assemble_mixed_contribution_simple_and_compound_both_render():
    """Mixed contributions: one simple Column + one CompoundColumn.
    Both should appear in the assembled list (compound expanded inline)."""
    from pluggable_protocol_tree.builtins.repetitions_column import (
        make_repetitions_column,
    )
    p = PluggableProtocolTreePlugin()
    simple = make_repetitions_column()
    p.contributed_columns = [simple, _make_compound()]
    ids = [c.model.col_id for c in p._assemble_columns()]
    # Simple column survives:
    assert ids.count("repetitions") >= 1   # builtins also include it
    # Both compound fields present:
    assert "ec_enabled" in ids
    assert "ec_count" in ids


def test_existing_single_cell_columns_still_assemble_unchanged():
    """Regression: PPT-3/4 single-cell columns continue to work."""
    p = PluggableProtocolTreePlugin()
    cols = p._assemble_columns()   # builtins only
    ids = [c.model.col_id for c in cols]
    assert "type" in ids
    assert "duration_s" in ids
    assert "electrodes" in ids


def test_compound_wait_for_topics_only_on_owner_field():
    """C1 regression: only the owner field advertises wait_for_topics
    so that bucketing in ProtocolExecutor._build_step_ctx doesn't see
    multiple columns at the same priority with the same topic."""
    h = BaseCompoundColumnHandler()
    h.priority = 25
    h.wait_for_topics = ["x/applied"]
    cc = CompoundColumn(
        model=_TwoFieldModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   IntSpinBoxColumnView(low=0, high=999),
        }),
        handler=h,
    )
    p = PluggableProtocolTreePlugin()
    p.contributed_columns = [cc]
    cols = [c for c in p._assemble_columns()
            if isinstance(c.handler, _CompoundFieldHandlerAdapter)]
    owner = next(c for c in cols if c.handler.is_owner)
    followers = [c for c in cols if not c.handler.is_owner]
    assert owner.handler.wait_for_topics == ["x/applied"]
    assert all(f.handler.wait_for_topics == [] for f in followers)

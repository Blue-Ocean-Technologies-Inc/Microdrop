"""Tests for the UI-edit codepath: MvcTreeModel.setData -> adapter ->
compound handler with field_id; per-cell get_flags(row) reads sibling
field values for conditional editability."""

from unittest.mock import MagicMock

from pyface.qt.QtCore import Qt
from traits.api import Bool, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel


class _DemoModel(BaseCompoundColumnModel):
    base_id = "demo"
    def field_specs(self):
        return [FieldSpec("ec_enabled", "Enabled", False),
                FieldSpec("ec_count",   "Count",   0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


class _SpyHandler(BaseCompoundColumnHandler):
    """Records every on_interact call as (row, field_id, value)."""
    def __init__(self):
        super().__init__()
        self.calls = []
    def on_interact(self, row, model, field_id, value):
        self.calls.append((row, field_id, value))
        return model.set_value(row, field_id, value)


class _CountCellViewWithGate(IntSpinBoxColumnView):
    """Read-only when the row's ec_enabled field is False — the
    cross-cell editability mechanism we're testing here."""
    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, "ec_enabled", False):
            flags &= ~Qt.ItemIsEditable
        return flags


def _build_manager():
    cc = CompoundColumn(
        model=_DemoModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   _CountCellViewWithGate(low=0, high=999),
        }),
        handler=_SpyHandler(),
    )
    cols = _expand_compound(cc)
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "ec_enabled": False, "ec_count": 0})
    return rm, cols, cc.handler


def test_setdata_on_compound_cell_calls_compound_handler_with_field_id():
    """Editing the count cell via setData must call compound_handler.on_interact
    with field_id='ec_count' and the new value."""
    rm, cols, handler = _build_manager()
    model = MvcTreeModel(rm)
    # Step row at index 0; column index = position of 'ec_count' in cols
    field_col_idx = next(i for i, c in enumerate(cols)
                         if c.model.col_id == "ec_count")
    step_index = model.index(0, field_col_idx)
    model.setData(step_index, 7, role=Qt.EditRole)
    assert handler.calls[-1][1] == "ec_count"
    assert handler.calls[-1][2] == 7


def test_count_cell_read_only_when_enabled_is_false():
    """The CountCellViewWithGate.get_flags(row) check returns flags
    WITHOUT Qt.ItemIsEditable when row.ec_enabled is False."""
    rm, cols, _ = _build_manager()
    count_col = next(c for c in cols if c.model.col_id == "ec_count")
    row = rm.root.children[0]
    row.ec_enabled = False
    flags = count_col.view.get_flags(row)
    assert not (flags & Qt.ItemIsEditable)


def test_count_cell_editable_when_enabled_is_true():
    """When ec_enabled flips to True, the count cell becomes editable."""
    rm, cols, _ = _build_manager()
    count_col = next(c for c in cols if c.model.col_id == "ec_count")
    row = rm.root.children[0]
    row.ec_enabled = True
    flags = count_col.view.get_flags(row)
    assert flags & Qt.ItemIsEditable


def test_setdata_on_owner_cell_does_not_double_fire_compound_handler():
    """Setting the FIRST (owner) field doesn't cause on_interact to
    fire twice. on_interact always fires per-cell-edit; the is_owner
    flag only gates execution hooks (on_step etc)."""
    rm, cols, handler = _build_manager()
    model = MvcTreeModel(rm)
    enabled_col_idx = next(i for i, c in enumerate(cols)
                           if c.model.col_id == "ec_enabled")
    step_index = model.index(0, enabled_col_idx)
    model.setData(step_index, True, role=Qt.CheckStateRole)
    # Exactly one on_interact call:
    enabled_calls = [c for c in handler.calls if c[1] == "ec_enabled"]
    assert len(enabled_calls) == 1

"""Interfaces for the compound column framework.

A compound column contributes N coupled cells that share one model +
one handler. Parallel to IColumn (does NOT extend it). Tree assembly
expands a compound contribution into N synthesized per-cell Column
instances at runtime; downstream consumers (RowManager, executor,
persistence, MvcTreeModel) keep speaking Column / IColumnModel.
"""

from typing import NamedTuple

from traits.api import Instance, Int, Interface, List, Str

from .i_column import IColumnView


class FieldSpec(NamedTuple):
    """One field of a compound column."""
    field_id: str        # row attribute name AND col_id of the rendered cell
    col_name: str        # column header label
    default_value: object   # applied at row construction


class ICompoundColumnModel(Interface):
    """Model owning N coupled fields. Each field becomes a row trait
    AND a visible cell. The handler sees all field values."""

    base_id = Str(desc="Logical name for the compound — appears in JSON "
                       "as 'compound_id' on each field's column entry.")

    def field_specs(self):
        """Returns ordered list[FieldSpec] of fields this compound contributes."""

    def trait_for_field(self, field_id):
        """Return the Traits TraitType for the given field. Same role as
        IColumnModel.trait_for_row but per-field."""

    def get_value(self, row, field_id): ...
    def set_value(self, row, field_id, value): ...
    def serialize(self, field_id, value): ...
    def deserialize(self, field_id, raw): ...


class ICompoundColumnView(Interface):
    """N per-cell views, one per field."""
    def cell_view_for_field(self, field_id):
        """Return the IColumnView for the given field."""


class ICompoundColumnHandler(Interface):
    """Five execution hooks (same as IColumnHandler) plus field-aware on_interact."""
    priority = Int(50)
    wait_for_topics = List(Str)

    def on_interact(self, row, model, field_id, value):
        """Default: model.set_value(row, field_id, value)."""

    def on_protocol_start(self, ctx): pass
    def on_pre_step(self, row, ctx): pass
    def on_step(self, row, ctx): pass
    def on_post_step(self, row, ctx): pass
    def on_protocol_end(self, ctx): pass


class ICompoundColumn(Interface):
    """Composition of model + view + handler."""
    model = Instance(ICompoundColumnModel)
    view = Instance(ICompoundColumnView)
    handler = Instance(ICompoundColumnHandler)

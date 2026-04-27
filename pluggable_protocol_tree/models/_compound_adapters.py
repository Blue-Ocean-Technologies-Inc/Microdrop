"""Internal: adapter shims that present a compound column's per-field
state as single-cell Column components. Used by _assemble_columns
expansion. Not part of the public API — callers should never construct
these directly; build a CompoundColumn and let _assemble_columns expand it.
"""

from traits.api import Bool, Instance, Str

from ..interfaces.i_compound_column import (
    ICompoundColumnHandler, ICompoundColumnModel,
)
from .column import BaseColumnHandler, BaseColumnModel


class _CompoundFieldAdapter(BaseColumnModel):
    """Single-cell IColumnModel facade for one field of a compound model.

    col_id, col_name, default_value are inherited Trait attributes from
    BaseColumnModel — set them at construction. By convention
    field_id == col_id (could differ but no reason to).
    compound_base_id is cached at construction so persistence doesn't
    need to round-trip through compound_model.base_id at serialize time.
    """
    compound_model = Instance(ICompoundColumnModel)
    field_id = Str
    is_owner = Bool(False)
    compound_base_id = Str

    def trait_for_row(self):
        return self.compound_model.trait_for_field(self.field_id)

    def get_value(self, row):
        return self.compound_model.get_value(row, self.field_id)

    def set_value(self, row, value):
        return self.compound_model.set_value(row, self.field_id, value)

    def serialize(self, value):
        return self.compound_model.serialize(self.field_id, value)

    def deserialize(self, raw):
        return self.compound_model.deserialize(self.field_id, raw)


class _CompoundFieldHandlerAdapter(BaseColumnHandler):
    """Single-cell IColumnHandler facade. on_interact translates the
    single-field call into the compound handler's field-aware call.
    Execution hooks fire only on the OWNER field (is_owner=True) so the
    compound's on_step / on_pre_step / etc. run exactly once per row,
    not N times.

    priority and wait_for_topics are mirrored from the compound handler
    at construction time so the executor's subscription aggregation in
    PluggableProtocolTreePlugin.start() picks up the right topics.
    """
    compound_handler = Instance(ICompoundColumnHandler)
    compound_model = Instance(ICompoundColumnModel)
    field_id = Str
    is_owner = Bool(False)

    def on_interact(self, row, model, value):
        # `model` is the per-field _CompoundFieldAdapter (passed in by
        # MvcTreeModel.setData via col.model). Ignore it — pass the real
        # compound_model to the compound handler so it sees its own model
        # type instead of the adapter wrapper.
        return self.compound_handler.on_interact(
            row, self.compound_model, self.field_id, value,
        )

    def on_protocol_start(self, ctx):
        if self.is_owner:
            self.compound_handler.on_protocol_start(ctx)

    def on_pre_step(self, row, ctx):
        if self.is_owner:
            self.compound_handler.on_pre_step(row, ctx)

    def on_step(self, row, ctx):
        if self.is_owner:
            self.compound_handler.on_step(row, ctx)

    def on_post_step(self, row, ctx):
        if self.is_owner:
            self.compound_handler.on_post_step(row, ctx)

    def on_protocol_end(self, ctx):
        if self.is_owner:
            self.compound_handler.on_protocol_end(ctx)


from .column import Column  # noqa: E402 — after class definitions to avoid circular
from ..interfaces.i_compound_column import ICompoundColumn  # noqa: E402


def _expand_compound(c: ICompoundColumn) -> list:
    """Expand a CompoundColumn contribution into N synthesized per-cell
    Column instances. The model + handler are shared via adapter shims
    so downstream consumers (RowManager, executor, MvcTreeModel,
    persistence) keep speaking single-cell Column / IColumnModel."""
    specs = c.model.field_specs()
    expanded = []
    for idx, spec in enumerate(specs):
        model_adapter = _CompoundFieldAdapter(
            col_id=spec.field_id,
            col_name=spec.col_name,
            default_value=spec.default_value,
            compound_model=c.model,
            field_id=spec.field_id,
            compound_base_id=c.model.base_id,
            is_owner=(idx == 0),
        )
        handler_adapter = _CompoundFieldHandlerAdapter(
            compound_handler=c.handler,
            compound_model=c.model,
            field_id=spec.field_id,
            is_owner=(idx == 0),
            priority=c.handler.priority,
            wait_for_topics=(list(c.handler.wait_for_topics or [])
                             if idx == 0 else []),
        )
        view = c.view.cell_view_for_field(spec.field_id)
        expanded.append(Column(
            model=model_adapter, view=view, handler=handler_adapter,
        ))
    return expanded

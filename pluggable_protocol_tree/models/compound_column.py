"""Base classes + composite for compound columns. Mirrors the structure
of models/column.py for single-cell columns. See spec section 2."""

from traits.api import Dict, HasTraits, Instance, Int, List, Str, provides

from ..interfaces.i_column import IColumnView
from ..interfaces.i_compound_column import (
    FieldSpec, ICompoundColumn, ICompoundColumnHandler,
    ICompoundColumnModel, ICompoundColumnView,
)


@provides(ICompoundColumnModel)
class BaseCompoundColumnModel(HasTraits):
    base_id = Str(desc="Logical compound name; persistence discriminator.")

    def field_specs(self) -> list:
        return []

    def trait_for_field(self, field_id):
        raise NotImplementedError(
            f"{type(self).__name__}.trait_for_field({field_id!r}) must be overridden"
        )

    def get_value(self, row, field_id):
        return getattr(row, field_id, None)

    def set_value(self, row, field_id, value):
        setattr(row, field_id, value)
        return True

    def serialize(self, field_id, value):
        return value

    def deserialize(self, field_id, raw):
        return raw


@provides(ICompoundColumnView)
class BaseCompoundColumnView(HasTraits):
    """Subclass and override cell_view_for_field, OR use DictCompoundColumnView
    for a static field_id → view dict."""

    def cell_view_for_field(self, field_id) -> IColumnView:
        raise NotImplementedError


class DictCompoundColumnView(BaseCompoundColumnView):
    """Cell views indexed by field_id. Raises KeyError for unknown fields."""
    cell_views = Dict(Str, Instance(IColumnView))

    def cell_view_for_field(self, field_id):
        return self.cell_views[field_id]


@provides(ICompoundColumnHandler)
class BaseCompoundColumnHandler(HasTraits):
    priority = Int(50)
    wait_for_topics = List(Str)
    model = Instance(ICompoundColumnModel)

    def on_interact(self, row, model, field_id, value):
        return model.set_value(row, field_id, value)

    def on_protocol_start(self, ctx): pass
    def on_pre_step(self, row, ctx): pass
    def on_step(self, row, ctx): pass
    def on_post_step(self, row, ctx): pass
    def on_protocol_end(self, ctx): pass


@provides(ICompoundColumn)
class CompoundColumn(HasTraits):
    """Composite. Auto-substitutes BaseCompoundColumnHandler if the
    handler kwarg is omitted; auto-wires handler.model = model."""
    model = Instance(ICompoundColumnModel)
    view = Instance(ICompoundColumnView)
    handler = Instance(ICompoundColumnHandler)

    def traits_init(self):
        if self.handler is None:
            self.handler = BaseCompoundColumnHandler()
        self.handler.model = self.model

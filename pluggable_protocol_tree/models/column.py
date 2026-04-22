"""Base model, handler, and composite for columns.

The 80%-case types. Plugin authors typically subclass BaseColumnModel to
declare a typed trait (see Task 9+ for built-in examples), and use
BaseColumnHandler as-is or override only the hooks they need. Column
itself is the composite that traits-wires model/view/handler together.
"""

from traits.api import (
    HasTraits, Instance, Str, Any, Int, List, Bool, provides, observe,
)

from pluggable_protocol_tree.interfaces.i_column import (
    IColumn, IColumnModel, IColumnView, IColumnHandler,
)


@provides(IColumnModel)
class BaseColumnModel(HasTraits):
    col_id = Str(desc="Stable id — used for storage, slicing, hook lookup")
    col_name = Str(desc="Display label for the column header")
    default_value = Any(None, desc="Value used on new-row insertion and as load-fallback")

    def trait_for_row(self):
        """Default: an Any trait seeded with default_value.

        Override in subclasses to use typed Traits (Float, Int, Str,
        List, ...) for proper validation and observer-friendliness.
        """
        return Any(self.default_value)

    def get_value(self, row):
        return getattr(row, self.col_id, None)

    def set_value(self, row, value):
        setattr(row, self.col_id, value)
        return True

    def serialize(self, value):
        """Identity for JSON-native types. Override for custom types."""
        return value

    def deserialize(self, raw):
        """Identity for JSON-native types. Override for custom types."""
        return raw


@provides(IColumnHandler)
class BaseColumnHandler(HasTraits):
    priority = Int(50)
    wait_for_topics = List(Str)

    # These are re-assigned by Column.traits_init so the handler can
    # reach its peers. Plugin authors generally do not set these.
    model = Instance(IColumnModel)
    view = Instance(IColumnView)

    def on_interact(self, row, model, value):
        """Default edit behaviour: write through to the model."""
        return model.set_value(row, value)

    # The five execution hooks — all no-ops by default.
    def on_protocol_start(self, ctx): pass
    def on_pre_step(self, row, ctx): pass
    def on_step(self, row, ctx): pass
    def on_post_step(self, row, ctx): pass
    def on_protocol_end(self, ctx): pass


@provides(IColumn)
class Column(HasTraits):
    """Composite bundling model + view + handler.

    `traits_init` wires them together so view.model, handler.model,
    handler.view are all populated without the plugin author having to
    think about it. Re-assigning any of the three updates the wiring.
    """
    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler)

    def traits_init(self):
        if self.handler is None:
            self.handler = BaseColumnHandler()
        self.view.model = self.model
        self.handler.model = self.model
        self.handler.view = self.view

    @observe("model", post_init=True)
    def _on_model_change(self, event):
        self.view.model = self.model
        self.handler.model = self.model

    @observe("view", post_init=True)
    def _on_view_change(self, event):
        self.view.model = self.model
        self.handler.view = self.view

    @observe("handler", post_init=True)
    def _on_handler_change(self, event):
        self.handler.model = self.model
        self.handler.view = self.view

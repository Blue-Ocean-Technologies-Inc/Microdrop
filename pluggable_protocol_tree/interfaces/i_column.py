"""Traits interfaces for protocol-tree columns.

Every column is a trio: model (semantics), view (presentation), handler
(behaviour). The IColumn interface bundles them. This split lets two
plugins reuse the same model with different views, or the same view with
different handlers, with no coupling.
"""

from traits.api import Interface, Str, Any, Int, Bool, Instance, List


class IColumnModel(Interface):
    """Semantic definition: what kind of value this column holds."""
    col_id = Str
    col_name = Str
    default_value = Any

    def trait_for_row(self):
        """Return the Traits TraitType (Float, Int, Str, List, ...) that
        this column contributes to the dynamic row class. Type validation
        and defaults live here."""

    def get_value(self, row):
        """Read the column's value off `row`."""

    def set_value(self, row, value):
        """Write `value` to the column on `row`. Returns True on success."""

    def serialize(self, value):
        """Convert a trait value to a JSON-native form."""

    def deserialize(self, raw):
        """Convert a JSON-native form back to a trait value."""


class IColumnView(Interface):
    """How the column looks and edits in the tree grid."""
    hidden_by_default = Bool(False)
    renders_on_group = Bool(True)

    def format_display(self, value, row):
        """String shown in the cell (DisplayRole)."""

    def get_flags(self, row):
        """Qt.ItemFlag bitmask for this cell on this row."""

    def get_check_state(self, value, row):
        """Qt.CheckState or None (returning None means no checkbox)."""

    def create_editor(self, parent, context):
        """Create a QWidget for editing. Return None for non-editable cells."""

    def set_editor_data(self, editor, value):
        """Push `value` into the editor widget."""

    def get_editor_data(self, editor):
        """Pull the current value out of the editor widget."""


class IColumnHandler(Interface):
    """Runtime behaviour. Five execution hooks + one UI-edit hook.

    Priority bucket (lower runs first, equal priorities run in parallel)
    applies to all five execution hooks in PPT-2 onward. In PPT-1 the
    hooks are defined but never invoked (no executor yet).
    """
    priority = Int(50)
    wait_for_topics = List(Str,
        desc="Topics this handler may call ctx.wait_for() on. Aggregated "
             "by core plugin for the executor's dramatiq subscription. "
             "Unused in PPT-1; reserved for PPT-2.")

    def on_interact(self, row, model, value):
        """Called when the UI commits an edit. Default: model.set_value."""

    def on_protocol_start(self, ctx): pass
    def on_pre_step(self, row, ctx): pass
    def on_step(self, row, ctx): pass
    def on_post_step(self, row, ctx): pass
    def on_protocol_end(self, ctx): pass


class IColumn(Interface):
    """Composition of model + view + handler."""
    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler)

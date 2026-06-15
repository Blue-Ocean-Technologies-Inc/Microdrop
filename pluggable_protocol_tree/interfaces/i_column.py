"""Traits interfaces for protocol-tree columns.

Every column is a trio: model (semantics), view (presentation), handler
(behaviour). The IColumn interface bundles them. This split lets two
plugins reuse the same model with different views, or the same view with
different handlers, with no coupling.
"""

from PySide6.QtCore import Signal

from traits.api import Interface, Str, Any, Float, Int, Bool, Instance, List


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
    """Runtime behaviour: the execution hooks plus one UI-edit hook.

    Priority bucket (lower runs first, equal priorities run in parallel)
    applies to all execution hooks. This interface is also implemented by
    execution-only "lifecycle handlers" (no column/view) that the executor
    runs alongside columns — see pluggable_protocol_tree/execution/lifecycle/.
    """

    priority = Int(50)
    wait_for_topics = List(
        Str,
        desc="Topics this handler may call ctx.wait_for() on. Aggregated "
        "by the plugin for the executor's dramatiq subscription.",
    )
    default_ack_time_s = Float(
        0.0,
        desc="Provider default (seconds) for this handler's "
        "acknowledgement wait, seeded into the Protocol Settings "
        "ack-wait grid under the column's id. 0.0 = the column "
        "has no ack wait to configure.",
    )
    ack_time_s = Float(
        0.0,
        desc="Live ack wait (seconds) read at wait time; the protocol "
        "dock pane pushes the Protocol Settings grid value here "
        "(ACK_WAIT_FOREVER pre-mapped to float('inf')). Starts at "
        "default_ack_time_s; 0 = don't wait.",
    )

    model = Instance(
        IColumnModel, desc="Wired by Column.traits_init; the handler's "
        "view of its own column semantics."
    )
    view = Instance(
        IColumnView, desc="Wired by Column.traits_init."
    )

    column_changed_signal = Instance(
        Signal, desc="Emit to signal parent tree model column needs refreshing"
    )
    trigger_column_change_when_wired = Bool(
        False,
        desc="When column_changed_signal is initialized, does it have to be triggered from a missed past event before it was wired to this handler.",
    )

    def on_interact(self, row, model, value):
        """Called when the UI commits an edit. Default: model.set_value."""

    def on_pre_protocol_start(self, ctx):
        """Once per run, before the first repetition (and before any
        on_protocol_start). For once-per-run setup that must bracket all
        repetitions (e.g. realtime-mode prep, logging start)."""

    def on_protocol_start(self, ctx):
        pass

    def on_pre_step(self, row, ctx):
        pass

    def on_step(self, row, ctx):
        pass

    def on_post_step(self, row, ctx):
        pass

    def on_protocol_end(self, ctx):
        pass

    def on_post_protocol_end(self, ctx):
        """Once per run, after the last repetition (and after every
        on_protocol_end). For once-per-run teardown (e.g. realtime-mode
        restore, logging stop)."""


class IColumn(Interface):
    """Composition of model + view + handler."""

    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler)

    id = Str(desc="Identity of this column UNIT (model+view+handler) for "
                  "unit-level maps like the ack-wait grid. Defaults to the "
                  "model's col_id; compound expansion overrides it with the "
                  "compound's base_id on every synthesized field cell.")

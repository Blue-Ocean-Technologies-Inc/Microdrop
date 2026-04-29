"""Force column — derived per-step force display in mN/m (read-only).

Force is never stored on rows or persisted to JSON. It is computed on
demand from the row's voltage trait and the process-wide
CalibrationCache singleton; both inputs change independently, so Task 5
will wire reactive Qt repaints from the dependency declarations on the
view (depends_on_row_traits + depends_on_event_source/_trait_name).
"""

from traits.api import Float, List as TraitList, Str

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)

from ..services.calibration_cache import cache
from ..services.force_math import force_for_step


class ForceColumnModel(BaseColumnModel):
    """Read-only derived column. Row trait is a placeholder; values are
    computed in get_value and never persisted."""

    def trait_for_row(self):
        # Required by build_row_type; never read — get_value computes
        # from cache + row.voltage.
        return Float(0.0)

    def get_value(self, row):
        c_per_a = cache.capacitance_per_unit_area()
        if c_per_a is None:
            return None
        return force_for_step(float(row.voltage), c_per_a)

    def serialize(self, value):
        return None

    def deserialize(self, raw):
        return None


class ForceColumnView(ReadOnlyLabelColumnView):
    renders_on_group = False
    hidden_by_default = False

    # Task 5 (MvcTreeModel reactive wiring) reads these to emit
    # dataChanged when dependencies change. Declared on the view (not
    # the model) so the wiring code lives next to display concerns.
    depends_on_row_traits = TraitList(Str, value=["voltage"])

    # Plain Python class attributes — a HasTraits singleton reference
    # and a string trait name. Task 5 probes via getattr so columns
    # without an event dependency can simply omit these.
    depends_on_event_source = cache
    depends_on_event_trait_name = "cache_changed"

    def format_display(self, value, row):
        return f"{value:.2f}" if value is not None else ""


def make_force_column():
    return Column(
        model=ForceColumnModel(
            col_id="force",
            col_name="Force (mN/m)",
            default_value=0.0,
        ),
        view=ForceColumnView(),
        handler=BaseColumnHandler(),
    )

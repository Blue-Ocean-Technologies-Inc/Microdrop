"""Force column — derived per-step force display in mN/m (read-only).

Force is never stored on rows or persisted to JSON. It is computed on
demand (in get_value) from the row's voltage trait and the latest
calibration capacitances, which the device viewer publishes into the
process-wide app globals.

Both inputs change independently, so two reactive paths repaint the
column:
- voltage edits: the view declares ``depends_on_row_traits = ["voltage"]``
  and MvcTreeModel emits a focused per-cell dataChanged.
- calibration changes: ForceColumnHandler listens for CALIBRATION_DATA
  and emits column_changed_signal, which MvcTreeModel turns into a
  column-wide repaint.
"""

import dramatiq
from dropbot_protocol_controls.consts import CALIBRATION_LISTENER_ACTOR_NAME
from traits.api import Float, List as TraitList, provides, Instance, Str

from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
    basic_listener_actor_routine,
)
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler,
    BaseColumnModel,
    Column,
)
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)
from ..consts import PKG_name

from ..services.force_math import force_for_step, current_full_electrode_capacitance_per_unit_area

from logger.logger_service import get_logger

logger = get_logger(__name__)


class ForceColumnModel(BaseColumnModel):
    """Read-only derived column. Row trait is a placeholder; values are
    computed in get_value and never persisted."""

    def trait_for_row(self):
        # Required by build_row_type; never read — get_value computes
        # from the calibration globals + row.voltage.
        return Float(0.0)

    def get_value(self, row):
        c_per_a = current_full_electrode_capacitance_per_unit_area()
        if c_per_a is None:
            return None
        return force_for_step(float(row.voltage), c_per_a)

    def serialize(self, value):
        return None

    def deserialize(self, raw):
        # The trait Float(0.0) rejects None; persistence calls
        # setattr(row, 'force', deserialize(raw)) unconditionally. Return
        # a valid Float placeholder — the value is meaningless (get_value
        # always recomputes from the calibration globals + row.voltage)
        # but it must satisfy the trait validator.
        return 0.0


class ForceColumnView(ReadOnlyLabelColumnView):
    renders_on_group = False
    hidden_by_default = False

    # MvcTreeModel reads this to emit a focused per-cell dataChanged
    # when the row's voltage changes. Declared on the view (not the
    # model) so the wiring code lives next to display concerns. The
    # calibration-driven repaint is handled separately by
    # ForceColumnHandler's column_changed_signal.
    depends_on_row_traits = TraitList(Str, value=["voltage"])

    def format_display(self, value, row):
        return f"{value:.2f}" if value is not None else ""


@provides(IDramatiqControllerBase)
class ForceColumnHandler(BaseColumnHandler):
    """Force-column handler that repaints the column on calibration changes.

    Subscribes (as a dramatiq listener) to CALIBRATION_DATA. The values
    themselves arrive via app globals and are read lazily in
    ForceColumnModel.get_value; this handler's only job is to nudge the
    tree model to repaint the column once new calibration lands, by
    emitting the column_changed_signal MvcTreeModel wires in.
    """

    ###################################################################################
    # IDramatiqControllerBase Interface
    ###################################################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = f"{PKG_name}_force_column"

    def traits_init(self):
        logger.info("Starting Protocol Tree Force Column Handler Listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=CALIBRATION_LISTENER_ACTOR_NAME,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    def _on_calibration_data_triggered(self, message):
        # Dispatched by basic_listener_actor_routine for the CALIBRATION_DATA
        # topic ("ui/calibration_data"). The payload is unused — get_value
        # re-reads the calibration globals on the repaint.
        if self.column_changed_signal is not None:
            self.column_changed_signal.emit()
        else:
            # Signal not wired yet (the tree model builds after the column);
            # defer the repaint until _wire_column_handlers_with_column_changed_signal
            # assigns the signal. See BaseColumnHandler._on_column_changed_signal_changed.
            self.trigger_column_change_when_wired = True


def make_force_column():
    return Column(
        model=ForceColumnModel(
            col_id="force",
            col_name="Force (mN/m)",
            default_value=0.0,
        ),
        view=ForceColumnView(),
        handler=ForceColumnHandler(),
    )

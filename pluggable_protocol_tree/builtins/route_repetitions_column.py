"""Route Reps column — number of times a step's ROUTES loop.

Feeds ``n_repeats`` into phase_math.iter_phases (loop-route cycles, and
open-route passes when Lin Reps is on). Distinct from the "Reps" column,
which repeats the whole step/group via row_manager._expand_frames. On a
step, total route plays = Reps x Route Reps. Inert on groups.

Edits prompt the user to hand control back from Route Reps Dur when the
row is in duration-controlled mode (``repeat_duration_controls`` True).
Confirming flips the flag back to False; cancelling rejects the edit.
This is the count-side of the same mode handoff the legacy protocol_grid
used between Repetitions and Repeat Duration.
"""

from traits.api import Int

from microdrop_application.dialogs.pyface_wrapper import YES, confirm

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RouteRepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this step's routes loop "
                           "(loop-route cycles / open-route passes).")


class RouteRepsHandler(BaseColumnHandler):
    """Count-side of the Route Reps <-> Route Reps Dur mode handoff."""

    def on_interact(self, row, model, value):
        if not bool(getattr(row, "repeat_duration_controls", False)):
            return model.set_value(row, value)
        choice = confirm(
            None,
            title="Switch to Route Reps Control",
            message=(
                "Switching back to Route Reps control will loop until the "
                "largest loop has completed all repetitions.<br><br>"
                "Route Reps Dur will be recalculated to match exactly "
                "(no idle time)."
            ),
            yes_label="Switch",
            no_label="Cancel",
        )
        if choice != YES:
            return False
        row.repeat_duration_controls = False
        return model.set_value(row, value)


def make_route_repetitions_column():
    return Column(
        model=RouteRepetitionsColumnModel(
            col_id="route_repetitions", col_name="Route Reps",
            default_value=1,
        ),
        # Bounds mirror the DV sidebar's RouteLayerManager.repetitions.
        view=IntSpinBoxColumnView(low=1, high=10000),
        handler=RouteRepsHandler(),
    )

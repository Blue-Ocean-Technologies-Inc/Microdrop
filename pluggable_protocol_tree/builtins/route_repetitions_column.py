"""Route Reps column — number of times a step's ROUTES loop.

Feeds ``n_repeats`` into phase_math.iter_phases (loop-route cycles, and
open-route passes when Lin Reps is on). Distinct from the "Reps" column,
which repeats the whole step/group via row_manager._expand_frames. On a
step, total route plays = Reps x Route Reps. Inert on groups.

While a row is in duration-controlled mode (``repeat_duration_controls``
True) this cell is LOCKED read-only via the per-row column-lock
mechanism (issue #541) — the lock is applied by a BaseRow observer on
the flag, so it also holds on protocol load and DV-sidebar sync. The
way back to count mode is editing Route Reps Dur to 0, which prompts
(see repeat_duration_column.py). No custom handler remains: edits can
only happen in count mode, where they are plain writes.
"""

from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RouteRepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this step's routes loop "
                           "(loop-route cycles / open-route passes).")


def make_route_repetitions_column():
    return Column(
        model=RouteRepetitionsColumnModel(
            col_id="route_repetitions", col_name="Route Reps",
            default_value=1,
        ),
        # Bounds mirror the DV sidebar's RouteLayerManager.repetitions.
        view=IntSpinBoxColumnView(low=1, high=10000),
    )

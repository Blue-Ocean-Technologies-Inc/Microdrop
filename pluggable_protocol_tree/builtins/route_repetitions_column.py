# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Route Reps column — number of times a step's ROUTES loop.

Feeds ``n_repeats`` into phase_math.iter_phases (loop-route cycles, and
open-route passes when Lin Reps is on). Distinct from the "Reps" column,
which repeats the whole step/group via row_manager._expand_frames. On a
step, total route plays = Reps x Route Reps. Inert on groups.

Route Reps and Route Reps Dur are mutually exclusive by last edit, like
the DV sidebar's pair: while Route Reps Dur is in control
(``repeat_duration_controls`` True) this cell shows the derived loop
count and stays editable — editing it hands control back to Route Reps,
and the repeat-duration reconciler refreshes Route Reps Dur with the
estimate.
"""

# Enthought library imports.
from traits.api import Int

# Microdrop package imports.
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler,
    BaseColumnModel,
    Column,
)
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RouteRepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(
            1,
            desc="Number of times this step's routes loop "
            "(loop-route cycles / open-route passes).",
        )


class RouteRepetitionsHandler(BaseColumnHandler):
    """A user edit takes loop control from Route Reps Dur."""

    def on_interact(self, row, model, value):
        row.repeat_duration_controls = False

        return model.set_value(row, value)


class RouteRepetitionsColumnView(IntSpinBoxColumnView):
    """Spinbox whose tooltip names the knob in control."""

    def get_tooltip(self, row):
        if isinstance(row, GroupRow):
            return None

        if getattr(row, "repeat_duration_controls", False):
            return (
                "Route Reps Dur is in control: this is the number of full "
                "loops that fit. Editing Route Reps takes control back."
            )

        return "Route Reps is in control. Editing Route Reps Dur takes over."


def make_route_repetitions_column():
    return Column(
        model=RouteRepetitionsColumnModel(
            col_id="route_repetitions",
            col_name="Route Reps",
            default_value=1,
        ),
        # Bounds mirror the DV sidebar's RouteLayerManager.repetitions.
        view=RouteRepetitionsColumnView(low=1, high=10000),
        handler=RouteRepetitionsHandler(),
    )

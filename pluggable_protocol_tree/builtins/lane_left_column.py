# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hidden lanes-in column. Extra lanes on the inside of the turn (or the
screen-left of travel when lanes_in_out is off) that a route's slug covers
beside its centreline. Zero, with lanes_out zero, is the plain trail."""

# Enthought library imports.
from traits.api import Int

# Microdrop package imports.
from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenIntSpinBoxColumnView,
)


class LaneLeftColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(
            int(self.default_value or 0),
            desc="Extra lanes inside the turn (screen-left with "
            "In/Out off) beside the route.",
        )


def make_lane_left_column():
    return Column(
        model=LaneLeftColumnModel(
            col_id="lane_left",
            col_name="Lanes In",
            default_value=0,
        ),
        # Bounds mirror the DV sidebar's RouteLayerManager.lane_left.
        view=HiddenIntSpinBoxColumnView(low=0, high=20),
    )

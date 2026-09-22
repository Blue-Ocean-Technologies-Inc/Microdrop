# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hidden lanes-in/out column. When True the lane counts are read as inside
and outside of the turn, so lanes hug the outer rung whichever way the
route bends; when False they are the screen-left and screen-right of
travel."""

# Enthought library imports.
from traits.api import Bool

# Microdrop package imports.
from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class LanesInOutColumnModel(BaseColumnModel):
    def trait_for_row(self):
        default = True if self.default_value is None else bool(self.default_value)

        return Bool(default, desc="Read the lanes as inside / outside of the turn.")


def make_lanes_in_out_column():
    return Column(
        model=LanesInOutColumnModel(
            col_id="lanes_in_out",
            col_name="In/Out",
            default_value=True,
        ),
        view=HiddenCheckboxColumnView(),
    )

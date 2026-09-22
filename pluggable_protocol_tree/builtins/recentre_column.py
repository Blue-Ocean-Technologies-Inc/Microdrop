# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hidden re-centre column. When True a rotation-locked slug is centred
on the route as it moves across its own heading; when False it keeps the
position it arrived in. Nothing to a slug that re-hangs."""

# Enthought library imports.
from traits.api import Bool

# Microdrop package imports.
from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class RecentreColumnModel(BaseColumnModel):
    def trait_for_row(self):
        default = True if self.default_value is None else bool(self.default_value)

        return Bool(default, desc="Centre a locked slug on the route across legs.")


def make_recentre_column():
    return Column(
        model=RecentreColumnModel(
            col_id="recentre",
            col_name="Re-centre",
            default_value=True,
        ),
        view=HiddenCheckboxColumnView(),
    )

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hidden linear-repeats column. When True, replay open routes
n_repeats times (n_repeats comes from the row's repetitions column)."""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class LinearRepeatsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="Replay open routes n_repeats times.")


def make_linear_repeats_column():
    return Column(
        model=LinearRepeatsColumnModel(
            col_id="linear_repeats", col_name="Lin Reps", default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )

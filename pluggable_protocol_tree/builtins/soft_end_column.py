# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hidden soft-end column. When True, append ramp-down phases that
shrink from trail_length back to 1 electrode."""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class SoftEndColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="Append ramp-down phases (trail_length --> 1).")


def make_soft_end_column():
    return Column(
        model=SoftEndColumnModel(
            col_id="soft_end", col_name="Soft End", default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )

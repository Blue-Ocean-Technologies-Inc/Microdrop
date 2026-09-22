# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hidden rotation-lock column. When True a route's slug keeps the
orientation it started with and only translates through corners; when
False it re-hangs behind its head along each new heading."""

# Enthought library imports.
from traits.api import Bool

# Microdrop package imports.
from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class RotationLockColumnModel(BaseColumnModel):
    def trait_for_row(self):
        default = True if self.default_value is None else bool(self.default_value)

        return Bool(default, desc="Keep the slug's orientation through corners.")


def make_rotation_lock_column():
    return Column(
        model=RotationLockColumnModel(
            col_id="rotation_lock",
            col_name="Rot Lock",
            default_value=True,
        ),
        view=HiddenCheckboxColumnView(),
    )

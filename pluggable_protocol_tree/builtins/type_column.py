# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Read-only column displaying each row's type ('step' or 'group')."""

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)


class TypeColumnModel(BaseColumnModel):
    def get_value(self, row):
        return row.row_type


class TypeColumnView(ReadOnlyLabelColumnView):
    def format_display(self, value, row):
        return row.row_type


def make_type_column():
    return Column(
        model=TypeColumnModel(col_id="type", col_name="Type"),
        view=TypeColumnView(),
    )

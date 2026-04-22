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

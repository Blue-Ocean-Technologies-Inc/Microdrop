"""Columns that are permanently shown by default"""

from .helpers import get_double_spinner_column
from ...models.column import BaseColumnModel
from .base_column_views import StringViewOnlyColumnView
from pluggable_protocol_tree.views.column.column import Column

class IDView(StringViewOnlyColumnView):

    def format_display(self, value, row):
        return row.id

    def create_editor(self, parent, context):
        return None


def get_id_column():
    return Column(model=BaseColumnModel(col_id="id", col_name="ID"), view=IDView())


def get_duration_column():
    return get_double_spinner_column(
        name="Duration (S)",
        id="duration_s",
        low=0.2,
        high=float("inf"),
        decimals=1,
        single_step=0.5,
    )

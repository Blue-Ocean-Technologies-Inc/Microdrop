"""Columns that are permanently shown by default"""
from .helpers import get_double_spinner_column
from ...models.column import BaseColumnModel
from .base_column_views import StringViewOnlyColumnView
from pluggable_protocol_tree.views.column.column import Column


class IDView(StringViewOnlyColumnView):

    def format_display(self, value, step):
        indices = []
        current_step = step

        while current_step.parent:
            try:
                # Add 1 because users expect 1-based indexing
                idx = current_step.parent.children.index(current_step) + 1
                indices.insert(0, str(idx))
            except ValueError:
                break
            current_step = current_step.parent

        return ".".join(indices) if indices else ""

    def create_editor(self, parent, context):
        return None


def get_id_column():
    return Column(model=BaseColumnModel(col_name="ID", col_id="id"), view=IDView())


def get_duration_column():
    return get_double_spinner_column(
                name="Duration (S)",
                id="duration",
                low=0.2,
                high=float('inf'),
                decimals=1,
                single_step=0.5
            )

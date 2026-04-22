"""Read-only dotted-path ID column.

Internal paths are 0-indexed tuples; the id column formats them
1-indexed so users see natural '1.2.3' rather than '0.1.2'. Orphan rows
(no parent) display the empty string.
"""

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)


class IdColumnModel(BaseColumnModel):
    def get_value(self, row):
        return row.path   # 0-indexed tuple

    def set_value(self, row, value):
        return False   # ID is derived, not assignable


class IdColumnView(ReadOnlyLabelColumnView):
    def format_display(self, value, row):
        path = row.path
        if not path:
            return ""
        return ".".join(str(i + 1) for i in path)


def make_id_column():
    return Column(
        model=IdColumnModel(col_id="id", col_name="ID"),
        view=IdColumnView(),
    )

"""Editable free-text Name column backed by the BaseRow.name trait."""

from traits.api import Str

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.string_edit import StringEditColumnView


class NameColumnModel(BaseColumnModel):
    def trait_for_row(self):
        """Name already exists on BaseRow — this Str here is safe to
        re-declare; Traits will use the subclass-level trait, preserving
        the default from the base."""
        return Str("Step")

    def get_value(self, row):
        return row.name

    def set_value(self, row, value):
        row.name = "" if value is None else str(value)
        return True


def make_name_column():
    return Column(
        model=NameColumnModel(col_id="name", col_name="Name", default_value="Step"),
        view=StringEditColumnView(),
    )

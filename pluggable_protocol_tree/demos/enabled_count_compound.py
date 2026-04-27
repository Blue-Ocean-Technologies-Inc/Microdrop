"""Synthetic demo compound column — drives the framework verification
demo (run_widget_compound_demo.py) and proves the framework works
end-to-end with a real Qt window.

Two fields: a Bool 'ec_enabled' and an Int 'ec_count' where the count
cell is read-only when ec_enabled is False. Demonstrates conditional
editability via cross-cell get_flags(row) lookups. NOT a builtin —
deletable once compound columns have a real consumer (PPT-5 magnet).
"""

from pyface.qt.QtCore import Qt
from traits.api import Bool, Int

from ..interfaces.i_compound_column import FieldSpec
from ..models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from ..views.columns.checkbox import CheckboxColumnView
from ..views.columns.spinbox import IntSpinBoxColumnView


class EnabledCountCompoundModel(BaseCompoundColumnModel):
    """Two coupled fields. The compound's base_id 'enabled_count_demo'
    appears in JSON as 'compound_id' on each field's column entry."""
    base_id = "enabled_count_demo"

    def field_specs(self):
        return [
            FieldSpec("ec_enabled", "Enabled", False),
            FieldSpec("ec_count",   "Count",   0),
        ]

    def trait_for_field(self, field_id):
        if field_id == "ec_enabled":
            return Bool(False)
        if field_id == "ec_count":
            return Int(0)
        raise KeyError(field_id)


class CountCellView(IntSpinBoxColumnView):
    """Read-only when the row's ec_enabled field is False. This is the
    canonical cross-cell editability pattern — get_flags(row) reads a
    SIBLING field's value off the row to gate this cell."""

    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, "ec_enabled", False):
            flags &= ~Qt.ItemIsEditable
        return flags


def make_enabled_count_compound():
    """Factory — returns a fresh CompoundColumn instance. Demo handler
    has no runtime side-effect (the synthetic column is for framework
    verification only)."""
    return CompoundColumn(
        model=EnabledCountCompoundModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   CountCellView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )

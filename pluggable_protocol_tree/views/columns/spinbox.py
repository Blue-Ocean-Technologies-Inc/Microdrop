"""Integer and floating-point spinbox column views.

Hints (low/high/decimals/single_step) live on the view — the model only
declares the type. Two plugins can reuse one model with different
spinbox hint configurations."""

import math

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QSpinBox, QDoubleSpinBox
from traits.api import Float, Int, provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class IntSpinBoxColumnView(BaseColumnView):
    low = Int(0, desc="Spinbox minimum")
    high = Int(1000, desc="Spinbox maximum")

    def format_display(self, value, row):
        if value is None:
            return ""
        return str(int(value))

    def get_flags(self, row):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(row, GroupRow):
            return base   # non-editable on groups
        return base | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        e = QSpinBox(parent)
        e.setMinimum(self.low)
        e.setMaximum(self.high)
        return e

    def set_editor_data(self, editor, value):
        editor.setValue(int(value) if value is not None else 0)

    def get_editor_data(self, editor):
        return editor.value()


@provides(IColumnView)
class DoubleSpinBoxColumnView(BaseColumnView):
    low = Float(0.0, desc="Spinbox minimum")
    high = Float(1000.0, desc="Spinbox maximum")
    decimals = Int(2, desc="Decimal places shown")
    single_step = Float(0.5, desc="Spinbox arrow step")

    def format_display(self, value, row):
        if value is None:
            return ""
        return f"{float(value):.{self.decimals}f}"

    def get_flags(self, row):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(row, GroupRow):
            return base
        return base | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        e = QDoubleSpinBox(parent)
        # QDoubleSpinBox doesn't accept math.inf — clamp to a very large value.
        e.setMinimum(self.low if math.isfinite(self.low) else -1e12)
        e.setMaximum(self.high if math.isfinite(self.high) else 1e12)
        e.setDecimals(self.decimals)
        e.setSingleStep(self.single_step)
        return e

    def set_editor_data(self, editor, value):
        editor.setValue(float(value) if value is not None else 0.0)

    def get_editor_data(self, editor):
        return editor.value()

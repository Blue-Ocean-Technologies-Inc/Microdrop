"""Combobox column view for fixed-choice (enum-like) string columns.

The selectable options are view configuration (the model only declares
the value type) so two plugins can reuse one model with different
choice sets — same split as the spinbox views' low/high hints.
"""

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QComboBox
from traits.api import List, Str, provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class ComboBoxColumnView(BaseColumnView):
    options = List(Str, desc="The selectable values, in display order")

    def format_display(self, value, row):
        if value is None:
            return ""
        return str(value)

    def get_flags(self, row):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(row, GroupRow):
            return base   # non-editable on groups
        return base | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        editor = QComboBox(parent)
        editor.addItems(list(self.options))
        return editor

    def set_editor_data(self, editor, value):
        index = editor.findText("" if value is None else str(value))
        editor.setCurrentIndex(max(0, index))

    def get_editor_data(self, editor):
        return editor.currentText()

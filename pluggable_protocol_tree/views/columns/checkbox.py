"""Checkbox column view for Bool-typed columns.

Checkboxes render only on step rows; groups show an empty cell.
Editing happens via the Qt check-role mechanism (no separate widget),
so create_editor returns None.
"""

from pyface.qt.QtCore import Qt
from traits.api import provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class CheckboxColumnView(BaseColumnView):
    def format_display(self, value, row):
        return ""   # cell has no text; check role carries the state

    def get_check_state(self, value, row):
        if isinstance(row, GroupRow):
            return None
        return Qt.Checked if value else Qt.Unchecked

    def get_flags(self, row):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(row, GroupRow):
            return base
        return base | Qt.ItemIsUserCheckable

    def create_editor(self, parent, context):
        return None   # Qt handles check-role edits directly

    def set_editor_data(self, editor, value):
        pass   # unused

    def get_editor_data(self, editor):
        pass   # unused

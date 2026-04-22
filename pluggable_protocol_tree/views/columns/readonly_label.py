"""Non-editable text column. Used for type, id, and any derived cells."""

from pyface.qt.QtCore import Qt
from traits.api import provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class ReadOnlyLabelColumnView(BaseColumnView):
    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable   # no editable flag

    def create_editor(self, parent, context):
        return None

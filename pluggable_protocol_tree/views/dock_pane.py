"""Pyface TaskPane hosting ProtocolTreeWidget.

Receives its column set from the plugin on construction."""

from pyface.tasks.api import TraitsDockPane
from traits.api import Instance, List, Str

from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.models.row_manager import RowManager


class PluggableProtocolDockPane(TraitsDockPane):
    id = "pluggable_protocol_tree.dock_pane"
    name = "Protocol"

    columns = List(Instance(IColumn))
    manager = Instance(RowManager)

    def create_contents(self, parent):
        from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget
        self.manager = RowManager(columns=self.columns)
        return ProtocolTreeWidget(self.manager, parent=parent)

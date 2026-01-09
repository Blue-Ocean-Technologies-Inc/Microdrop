from traits.api import List, Instance

from .tree_widget import ProtocolEditorWidget
from ..interfaces.i_column import IColumn
from ..models.row import GroupRow

from pyface.tasks.dock_pane import DockPane

from ..consts import PKG


class ProtocolPane(DockPane):
    id = f"{PKG}.pane"
    name = "Protocol Editor"

    # Dependencies injected by Envisage Plugins
    columns = List(IColumn)
    root_step = Instance(GroupRow)

    def create_contents(self, parent):
        """
        Envisage calls this to get the Qt Control.
        We simply return our standalone widget.
        """
        return ProtocolEditorWidget(parent=parent, columns=self.columns)

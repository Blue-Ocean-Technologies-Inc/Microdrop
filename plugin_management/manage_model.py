"""Qt-free model for the Manage Plugins dialog: one row per plugin group."""
from traits.api import Any, Bool, HasTraits, Instance, List, Str

from .group_manager import PluginGroupManager


class GroupRow(HasTraits):
    """One toggleable plugin group as shown in the dialog."""
    name = Str()
    label = Str()
    enabled = Bool(False)


class ManagePluginsModel(HasTraits):
    """Rows snapshotting the manager's groups; ``desired()`` reads the edited
    checkboxes back as the reconcile target."""

    manager = Instance(PluginGroupManager)
    rows = List(Instance(GroupRow))

    #: The Envisage application the Apply reconciles against.
    application = Any()

    def _rows_default(self):
        return [
            GroupRow(name=group.name, label=group.label, enabled=group.loaded)
            for group in self.manager.groups.values()
        ]

    def desired(self):
        """{group_name: enabled} from the current checkbox states."""
        return {row.name: row.enabled for row in self.rows}

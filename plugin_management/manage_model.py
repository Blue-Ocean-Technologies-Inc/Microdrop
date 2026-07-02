"""Qt-free model for the Manage Plugins window.

One row per plugin group (with its enable state) plus the enable/uninstall
operations the controller invokes. No Qt, no dialogs, no threading — the
controller (a Handler) owns those.
"""
from traits.api import Any, Bool, HasTraits, Instance, List, Str

from . import package_installer
from .group_manager import PluginGroupManager
from logger.logger_service import get_logger

logger = get_logger(__name__)


class GroupRow(HasTraits):
    """One toggleable plugin group as shown in the dialog."""
    name = Str()
    label = Str()
    enabled = Bool(False)


class ManagePluginsModel(HasTraits):
    """Rows snapshotting the manager's groups + the operations the controller
    invokes; ``desired()`` reads the edited checkboxes back as the reconcile
    target."""

    manager = Instance(PluginGroupManager)
    rows = List(Instance(GroupRow))

    #: The Envisage application the Apply reconciles against.
    application = Any()

    def _rows_default(self):
        return self._build_rows()

    def refresh(self):
        self.rows = self._build_rows()

    def _build_rows(self):
        return [
            GroupRow(name=group.name, label=group.label or group.name,
                     enabled=group.loaded)
            for group in self.manager.groups.values()
        ]

    def desired(self):
        """{group_name: enabled} from the current checkbox states."""
        return {row.name: row.enabled for row in self.rows}

    def apply(self):
        """Commit enable/disable as a live hot-load (no relaunch)."""
        self.manager.apply(self.application, self.desired())

    def installed_plugins(self):
        """[(manifest_name, label, dist_name, [group_names])] — the
        uninstallable (non-bundled) plugins."""
        return self.manager.installed_plugins()

    def pre_uninstall(self, manifest_name):
        """Hot-unload + deregister a plugin's groups before its package is
        removed, so declining the relaunch doesn't leave dead groups
        loaded/registered."""
        for name in [n for n, g in self.manager.groups.items()
                     if g.manifest_name == manifest_name]:
            if self.manager.is_loaded(name):
                self.manager.disable(self.application, name)
        self.manager.deregister_plugin(manifest_name)

    def do_uninstall(self, dist_name):
        """Worker-thread safe: remove the package (no trait mutation)."""
        package_installer.uninstall_package(dist_name)

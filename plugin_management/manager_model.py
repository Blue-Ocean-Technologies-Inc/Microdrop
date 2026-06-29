"""Qt-free model for the Manage Plugins window.

Tracks the plugin GROUPS discovered from the manifests (one row per group, with
its enable state) plus the enable/install/uninstall operations the controller
invokes. No Qt, no dialogs, no threading — the controller (a Handler) owns those.
"""
from traits.api import Any, Bool, HasTraits, Instance, List, Str

from plugin_management import package_installer
from logger.logger_service import get_logger

logger = get_logger(__name__)


class GroupRow(HasTraits):
    """One plugin group from a manifest: its name/label + whether it's enabled."""
    name = Str()
    label = Str()
    enabled = Bool(False)


class PluginManagerModel(HasTraits):
    """The plugin groups + the operations the controller invokes."""

    manager = Any()                              # IPluginGroupManager service
    groups = List(Instance(GroupRow))

    def _groups_default(self):
        return self._build_groups()

    def refresh(self):
        self.groups = self._build_groups()

    def _build_groups(self):
        return [GroupRow(name=g.name, label=g.label or g.name, enabled=g.loaded)
                for g in self.manager.groups.values()]

    def desired_state(self):
        """{group_name: enabled} for every group."""
        return {row.name: row.enabled for row in self.groups}

    def apply(self, task):
        """Commit enable/disable as a live hot-load (no relaunch)."""
        self.manager.apply(task, self.desired_state())

    def installed_plugins(self):
        """[(manifest_name, label, dist_name, [group_names])] — the uninstallable
        (non-bundled) plugins."""
        return self.manager.installed_plugins()

    def pre_uninstall(self, task, manifest_name):
        """Hot-unload + deregister a plugin's groups before its package is removed,
        so declining the relaunch doesn't leave dead groups loaded/registered."""
        for name in [n for n, g in self.manager.groups.items()
                     if g.manifest_name == manifest_name]:
            if self.manager.is_loaded(name):
                self.manager.disable(task, name)
        self.manager.deregister_plugin(manifest_name)

    def do_uninstall(self, dist_name):
        package_installer.uninstall_package(dist_name)

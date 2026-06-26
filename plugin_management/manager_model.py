"""Qt-free model for the Manage Plugins window: per-plugin row state + the
enable/disable/install/uninstall business logic. No Qt, no dialogs, no threading
(the controller owns those). Mutated only on the GUI thread."""
from traits.api import Any, Bool, HasTraits, Instance, List, Str, observe

from plugin_management import package_installer
from logger.logger_service import get_logger

logger = get_logger(__name__)


class OptionalGroupToggle(HasTraits):
    """One optional group's checkbox (e.g. magnet 'Backend')."""
    group_name = Str()
    toggle_label = Str()
    on = Bool(False)


class PluginRow(HasTraits):
    """One installed plugin (manifest) — its enable state + optional toggles."""
    manifest_name = Str()
    label = Str()
    version = Str()
    bundled = Bool(False)                       # app's own dist -> not uninstallable
    core_groups = List(Str)                     # enabled whenever 'enabled' is on
    optionals = List(Instance(OptionalGroupToggle))
    enabled = Bool(False)

    @observe("enabled")
    def _auto_check_optionals(self, event):
        if event.new:                            # 'Enable' auto-checks every optional
            for opt in self.optionals:
                opt.on = True

    def desired(self):
        """{group_name: bool} for this plugin's groups."""
        out = {g: self.enabled for g in self.core_groups}
        for opt in self.optionals:
            out[opt.group_name] = self.enabled and opt.on
        return out


class PluginManagerModel(HasTraits):
    """Rows for every installed plugin + the operations the controller invokes."""
    manager = Any()                             # IPluginGroupManager
    rows = List(Instance(PluginRow))

    def _rows_default(self):
        return self._build_rows()

    def refresh(self):
        self.rows = self._build_rows()

    def _build_rows(self):
        by_manifest = {}
        order = []
        for group in self.manager.groups.values():
            key = group.manifest_name
            if key not in by_manifest:
                by_manifest[key] = []
                order.append(key)
            by_manifest[key].append(group)
        installed = {e[0] for e in self.manager.installed_plugins()}
        rows = []
        for key in order:
            groups = by_manifest[key]
            core = [g.name for g in groups if not g.optional]
            optionals = [OptionalGroupToggle(group_name=g.name,
                                             toggle_label=g.toggle_label or g.name,
                                             on=g.loaded)
                         for g in groups if g.optional]
            any_core_loaded = any(g.loaded for g in groups if not g.optional)
            first = groups[0]
            rows.append(PluginRow(
                manifest_name=key,
                label=first.manifest_label or key,
                version=first.manifest_version,
                bundled=key not in installed,
                core_groups=core,
                optionals=optionals,
                enabled=any_core_loaded or any(o.on for o in optionals),
            ))
        return rows

    def desired_state(self):
        """{group_name: bool} across every plugin (for manager.apply)."""
        desired = {}
        for row in self.rows:
            desired.update(row.desired())
        return desired

    def apply(self, task):
        """Commit enable/disable as a live hot-load (no relaunch)."""
        self.manager.apply(task, self.desired_state())

    def installed_rows(self):
        """Rows the user can uninstall (non-bundled)."""
        return [r for r in self.rows if not r.bundled]

    # --- operations the controller runs on a worker thread -------------
    def preview(self, conda_path):
        return package_installer.read_conda_preview(conda_path)

    def do_install(self, conda_path):
        return package_installer.install_conda_file(conda_path)

    def do_uninstall(self, name):
        package_installer.uninstall_package(name)

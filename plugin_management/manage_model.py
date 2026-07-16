"""Qt-free model for the Manage Plugins window.

One row per plugin group (with its enable state) plus the enable/uninstall
operations the controller invokes. No Qt, no dialogs, no threading — the
controller (a Handler) owns those.
"""
import html

from traits.api import Any, Bool, Event, HasTraits, Instance, List, Str, observe

from . import package_installer
from .browse_model import _version_key, _DETAILS_CSS
from .group_manager import PluginGroupManager
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _available_versions(dist_name, channel, current=""):
    """Versions of ``dist_name`` present in the cached ``channel`` package list,
    newest first. Always includes the currently-installed ``current`` version
    so the dropdown can preselect it even when the channel cache is stale or
    missing that build."""
    versions = {str(pkg.get("version", ""))
                for pkg in channel
                if pkg.get("name") == dist_name and pkg.get("version")}
    if current:
        versions.add(current)
    return sorted((v for v in versions if v), key=_version_key, reverse=True)


class GroupRow(HasTraits):
    """One toggleable plugin group as shown in the dialog."""
    name = Str()
    label = Str()
    enabled = Bool(False)


class InstalledPackageRow(HasTraits):
    """One installed plugin *package* in the Installed Packages table.

    ``version`` is the current/selected version — the controller observes it
    and installs the chosen build. The three Events are fired by the table's
    glyph columns; the controller observes them to open docs / upgrade /
    uninstall. Qt-free."""
    name = Str()            # package (distribution) name, shown in the table
    dist_name = Str()       # join key for versions + docs (== name here)
    label = Str()           # friendly manifest label, used in dialogs
    manifest_name = Str()
    group_names = List(Str)

    version = Str()                 # current / selected version
    available_versions = List(Str)  # dropdown choices, newest first
    doc_url = Str()                 # repo/docs URL, "" until the plugin re-releases

    open_docs = Event()
    upgrade = Event()
    uninstall = Event()


def format_installed_details_html(row):
    """Styled HTML details for an installed package (shown in the details pane).
    The documentation URL is a real ``<a href>`` the HTMLEditor opens in the
    system browser; every value is HTML-escaped. Reuses the browse panel's CSS
    so both details views look the same in light/dark."""
    def esc(value):
        return html.escape(str(value if value is not None else ""))

    doc = (f'<a href="{esc(row.doc_url)}">{esc(row.doc_url)}</a>' if row.doc_url
           else "<i>Available after the plugin's next release.</i>")
    versions = ", ".join(esc(v) for v in row.available_versions) or esc(row.version)
    groups = ", ".join(esc(g) for g in row.group_names) or "—"
    detail_rows = [
        ("Package", esc(row.dist_name)),
        ("Installed version", esc(row.version)),
        ("Available versions", versions),
        ("Documentation", doc),
        ("Plugin groups", groups),
    ]
    row_html = "".join(f"<tr><th>{label}</th><td>{value}</td></tr>"
                       for label, value in detail_rows)
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{_DETAILS_CSS}</style></head><body>"
            f"<h2>{esc(row.label or row.dist_name)}</h2><table>{row_html}</table>"
            f"</body></html>")


class ManagePluginsModel(HasTraits):
    """Rows snapshotting the manager's groups + the operations the controller
    invokes; ``desired()`` reads the edited checkboxes back as the reconcile
    target."""

    manager = Instance(PluginGroupManager)
    rows = List(Instance(GroupRow))
    installed_rows = List(Instance(InstalledPackageRow))

    #: Row selected in the Installed Packages table + its details-pane HTML.
    installed_selected = Instance(InstalledPackageRow)
    installed_details_text = Str()

    #: The Envisage application the Apply reconciles against.
    application = Any()

    @observe("installed_selected")
    def _update_installed_details(self, event):
        """Fill the details pane for the selected installed package (blank when
        nothing is selected)."""
        self.installed_details_text = (
            format_installed_details_html(self.installed_selected)
            if self.installed_selected else "")

    def _rows_default(self):
        return self._build_rows()

    def _installed_rows_default(self):
        return self._build_installed_rows()

    def refresh(self):
        self.rows = self._build_rows()

    def refresh_installed(self):
        self.installed_rows = self._build_installed_rows()

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

    def _build_installed_rows(self):
        """One row per installed plugin package, joining the manager's
        installed-plugin list with each dist's current version
        (``installed_plugin_dists``), available versions (cached channel index),
        and documentation URL (``documentation_url``)."""
        dists = package_installer.installed_plugin_dists()
        channel = package_installer.read_cached_index()
        rows = []
        for manifest_name, label, dist_name, group_names in self.installed_plugins():
            current = dists.get(dist_name, "")
            rows.append(InstalledPackageRow(
                name=dist_name,
                dist_name=dist_name,
                label=label,
                manifest_name=manifest_name,
                group_names=list(group_names),
                version=current,
                available_versions=_available_versions(dist_name, channel, current),
                doc_url=package_installer.documentation_url(dist_name),
            ))
        return rows

    def apply_channel_data(self, channel):
        """GUI-thread: refresh each row's available versions from freshly
        fetched ``channel`` data (the result of ``do_search_channel``)."""
        for row in self.installed_rows:
            row.available_versions = _available_versions(
                row.dist_name, channel, row.version)

    # --- worker-thread safe ops (no trait mutation) ---
    def do_install_version(self, dist_name, version):
        """Install a specific version of a package (version dropdown select)."""
        return package_installer.install_from_channel(dist_name, version=version)

    def do_upgrade(self, dist_name):
        """Upgrade a package to the latest channel version (upgrade button)."""
        return package_installer.upgrade_package(dist_name)

    def do_search_channel(self):
        """Re-fetch the channel package list (Refresh Versions). Returns the
        data; the controller applies it on the GUI thread."""
        return package_installer.search_channel()

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
        return package_installer.uninstall_package(dist_name)

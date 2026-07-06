"""Model for the launch update-check dialog: the diff between the fresh
channel list, the previous launch's cached copy, and the installed set —
plus the worker-safe bulk update.

Qt-free (project MVC rule): nothing here imports Qt/pyface or mutates
traits off the GUI thread; ``do_update_all`` only returns data.
"""
import html

from traits.api import Bool, HasTraits, Instance, List, Str, Tuple

from logger.logger_service import get_logger

from . import package_installer
from .browse_model import _version_key

logger = get_logger(__name__)

#: Hint appended under the new-plugins list (install path lives elsewhere).
NEW_PLUGINS_HINT = (
    "<br><i>Install new plugins via Tools ▸ Manage Plugins ▸ "
    "Browse.</i>"
)


def _latest_by_name(packages) -> dict:
    """Collapse a raw channel package list to {name: latest version str}."""
    latest = {}
    for pkg in packages:
        name = pkg.get("name")
        if not name:
            continue
        version = str(pkg.get("version", ""))
        if name not in latest or _version_key(version) > _version_key(latest[name]):
            latest[name] = version
    return latest


class UpdateReport(HasTraits):
    """What the launch check found. ``updates`` rows are
    (name, installed_version, latest_version); ``new_plugins`` rows are
    (name, latest_version)."""

    updates = List(Tuple(Str, Str, Str))
    new_plugins = List(Tuple(Str, Str))

    @property
    def has_content(self):
        return bool(self.updates or self.new_plugins)


def compute_update_report(old, new, installed) -> UpdateReport:
    """Diff the fresh channel list against the installed set and the
    previous launch's cached copy.

    - update: installed package whose channel latest is newer than the
      installed version.
    - new plugin: channel package neither installed nor present in the OLD
      cached list. With no old cache (first launch) new-plugin detection
      is skipped entirely — the fetch just wrote the baseline — so a fresh
      install doesn't report every package as "new".
    """
    new_latest = _latest_by_name(new)
    old_names = set(_latest_by_name(old))
    updates = [
        (name, installed[name], latest)
        for name, latest in sorted(new_latest.items())
        if name in installed
        and _version_key(latest) > _version_key(installed[name])
    ]
    new_plugins = []
    if old_names:                       # first launch: baseline only
        new_plugins = [
            (name, latest)
            for name, latest in sorted(new_latest.items())
            if name not in installed and name not in old_names
        ]
    return UpdateReport(updates=updates, new_plugins=new_plugins)


class UpdateDialogModel(HasTraits):
    """Rows shown by the update dialog + the worker-safe bulk update."""

    report = Instance(UpdateReport)

    updates_html = Str()
    new_plugins_html = Str()
    has_updates = Bool(False)
    has_new = Bool(False)

    def traits_init(self):
        report = self.report
        self.has_updates = bool(report.updates)
        self.has_new = bool(report.new_plugins)
        self.updates_html = "<br>".join(
            f"<b>{html.escape(name)}</b>: {html.escape(installed)} "
            f"→ {html.escape(latest)}"
            for name, installed, latest in report.updates
        )
        if report.new_plugins:
            self.new_plugins_html = "<br>".join(
                f"<b>{html.escape(name)}</b> (v{html.escape(version)})"
                for name, version in report.new_plugins
            ) + NEW_PLUGINS_HINT

    def do_update_all(self):
        """Worker-thread safe: install the latest version of every listed
        update. Returns (succeeded names, [(name, error) failures])."""
        succeeded, failed = [], []
        for name, _installed, _latest in self.report.updates:
            try:
                package_installer.install_from_channel(name)
                succeeded.append(name)
            except package_installer.InstallError as e:
                logger.warning(f"update of {name} failed: {e}")
                failed.append((name, str(e)))
        return succeeded, failed

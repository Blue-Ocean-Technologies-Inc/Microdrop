"""Handler for the Manage Plugins window: the action-button handlers + the
per-row installed-package actions + the UI glue (dialogs, worker-thread
progress, relaunch). The model holds state/logic; this holds the flow. In each
action handler, ``info.object`` is the model.

Per-row actions (open docs / change version / upgrade / uninstall) are driven by
Events on the ``InstalledPackageRow`` objects, fired by the table's glyph and
dropdown columns; ``init`` wires observers on the model's ``installed_rows`` so
those Events land here, where dialogs + threading are allowed.
"""
import webbrowser

from traits.api import Instance
from pyface.tasks.api import Task
from pyface.qt.QtWidgets import QToolBar
from pyface.qt.QtGui import QFont

from microdrop_application.dialogs.pyface_wrapper import (
    confirm, error as error_dialog, YES, escape_html_multiline)
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_utils.threaded_progress import run_with_wait
from microdrop_utils.traitsui_qt_helpers import SafeCancelTableHandler
from logger.logger_service import get_logger

#: Point size of the Material Symbols glyph on the Refresh toolbar button.
REFRESH_ICON_POINT_SIZE = 16

from .browse_model import BrowsePluginsModel
from .browse_view import browse_view
from .browse_controller import BrowsePluginsHandler
from .relaunch import confirm_and_relaunch

logger = get_logger(__name__)


def _esc(s):
    return escape_html_multiline(str(s))


class ManagePluginsController(SafeCancelTableHandler):
    """Handles the Manage Plugins view's actions over the model (info.object)."""

    task = Instance(Task)

    # --- lifecycle: wire per-row installed-package Events -----------------
    def init(self, info):
        model = info.object
        self._model = model
        # Guards the version observer while we programmatically revert a
        # cancelled selection (so the revert doesn't re-prompt).
        self._suppress_version = False
        model.observe(self._on_open_docs, "installed_rows:items:open_docs")
        model.observe(self._on_version_selected, "installed_rows:items:version")
        model.observe(self._on_upgrade, "installed_rows:items:upgrade")
        model.observe(self._on_uninstall, "installed_rows:items:uninstall")
        super().init(info)            # Escape deselects instead of closing
        self._style_toolbar(info)
        return True

    def _style_toolbar(self, info):
        """Render the Refresh toolbar action as a Material Symbols glyph by
        giving the toolbar the icon font (its action's label is the glyph)."""
        control = getattr(info.ui, "control", None)
        if control is None:
            return
        for toolbar in control.findChildren(QToolBar):
            toolbar.setFont(QFont(ICON_FONT_FAMILY, REFRESH_ICON_POINT_SIZE))

    # --- Apply: live hot-load, no relaunch ---
    def apply_changes(self, info):
        try:
            info.object.apply()
            info.object.refresh()
        except Exception as e:
            logger.exception("apply enable/disable failed")
            error_dialog(parent=None, title="Apply failed", message=str(e))

    # --- Install: open the Browse Plugins dialog (lists the remote channel) ---
    def install_plugin(self, info):
        model = BrowsePluginsModel()
        model.edit_traits(view=browse_view,
                          handler=BrowsePluginsHandler(task=self.task),
                          kind="livemodal")

    # --- Refresh Versions: re-fetch the channel, update the dropdowns ---
    def refresh_versions(self, info):
        model = info.object
        self._run(model.do_search_channel,
                  title="Refreshing versions",
                  message="Searching the plugin channel…",
                  done=lambda data: model.apply_channel_data(data))

    def do_close(self, info):
        info.ui.dispose()

    # --- per-row installed-package actions -------------------------------
    def _on_open_docs(self, event):
        row = event.object
        if row.doc_url:
            webbrowser.open(row.doc_url)

    def _on_version_selected(self, event):
        if self._suppress_version:
            return
        row = event.object
        new_version, old_version = event.new, event.old
        if not new_version or new_version == old_version:
            return
        if confirm(parent=None, title="Install version?",
                   message=f"Install <b>{_esc(row.label)}</b> version "
                           f"<b>{_esc(new_version)}</b>? This changes the package "
                           f"in the environment.", cancel=False) != YES:
            self._set_row_version(row, old_version)  # revert the dropdown
            return
        label, dist = row.label, row.dist_name
        self._run(lambda: self._model.do_install_version(dist, new_version),
                  title="Installing version",
                  message=f"Installing {label} {new_version}…",
                  done=lambda r: (self._model.refresh_installed(),
                                  self._after_change(
                                      f"Installed <b>{_esc(label)}</b> "
                                      f"{_esc(new_version)}.")))

    def _on_upgrade(self, event):
        row = event.object
        latest = row.available_versions[0] if row.available_versions else ""
        label, dist = row.label, row.dist_name
        target = f" (<b>{_esc(latest)}</b>)" if latest else ""
        if confirm(parent=None, title="Upgrade plugin?",
                   message=f"Upgrade <b>{_esc(label)}</b> to the latest "
                           f"version{target}?", cancel=False) != YES:
            return
        self._run(lambda: self._model.do_upgrade(dist),
                  title="Upgrading plugin", message=f"Upgrading {label}…",
                  done=lambda r: (self._model.refresh_installed(),
                                  self._after_change(
                                      f"Upgraded <b>{_esc(label)}</b>.")))

    def _on_uninstall(self, event):
        row = event.object
        label, dist, manifest = row.label, row.dist_name, row.manifest_name
        if confirm(parent=None, title="Uninstall Plugin?",
                   message=f"Uninstall <b>{_esc(label)}</b>? This removes its "
                           f"package from the environment.", cancel=False) != YES:
            return
        self._model.pre_uninstall(manifest)
        self._run(lambda: self._model.do_uninstall(dist),
                  title="Uninstalling plugin", message=f"Removing {label}…",
                  done=lambda r: (self._model.refresh_installed(),
                                  self._after_change(
                                      f"Uninstalled <b>{_esc(label)}</b>.")))

    # --- helpers ---
    def _run(self, work, *, title, message, done):
        run_with_wait(work, title=title, message=message, on_success=done,
                      on_error=lambda e: error_dialog(
                          parent=None, title=title, message=str(e)))

    def _after_change(self, msg_html):
        confirm_and_relaunch(self.task, msg_html)

    def _set_row_version(self, row, version):
        """Revert a cancelled dropdown selection without re-triggering the
        install prompt."""
        self._suppress_version = True
        try:
            row.version = version
        finally:
            self._suppress_version = False

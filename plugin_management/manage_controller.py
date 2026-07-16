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

from traits.api import Instance, Button, Bool, Str, observe
from pyface.tasks.api import Task
from pyface.qt.QtWidgets import QToolBar, QSplitter, QWidget
from pyface.qt.QtGui import QFont
from pyface.qt.QtCore import QTimer

from microdrop_application.dialogs.pyface_wrapper import (
    confirm, error as error_dialog, YES, escape_html_multiline)
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_utils.threaded_progress import run_with_wait
from microdrop_utils.traitsui_qt_helpers import SafeCancelTableController
from logger.logger_service import get_logger

#: Point size of the Material Symbols glyph on the Refresh toolbar button.
REFRESH_ICON_POINT_SIZE = 16
#: Even, minimal gap (px) around the Installed Packages collapse button — the
#: HSplit handle width and the pane layout spacing are both set to this.
INSTALLED_SPLIT_GAP = 4

from .browse_model import BrowsePluginsModel
from .browse_view import browse_view
from .browse_controller import BrowsePluginsHandler
from .relaunch import confirm_and_relaunch

logger = get_logger(__name__)


def _esc(s):
    return escape_html_multiline(str(s))


class ManagePluginsController(SafeCancelTableController):
    """Handles the Manage Plugins view's actions over the model (info.object)."""

    task = Instance(Task)

    # --- Installed Packages details-pane collapse (state lives on the handler;
    #     the view binds the button + visible_when to these) ---
    toggle_details = Button()
    details_shown = Bool(False)                  # collapsed by default
    details_btn_label = Str("chevron_left")      # points the way the pane moves

    # Guards the version observer while we programmatically revert a
    # cancelled selection (so the revert doesn't re-prompt).
    _suppress_version = Bool(False)

    # --- lifecycle: wire per-row installed-package Events -----------------
    def init(self, info):
        super().init(info)            # Escape deselects instead of closing
        self._style_toolbar(info)
        self._tighten_splitters(info.ui.control)
        return True

    # --- details-pane collapse ---
    @observe("toggle_details")
    def _on_toggle_details(self, event):
        self.details_shown = not self.details_shown

    @observe("details_shown")
    def _on_details_shown(self, event):
        # chevron_right when shown (click collapses it rightward), chevron_left
        # when hidden (click brings it back in).
        self.details_btn_label = "chevron_right" if self.details_shown else "chevron_left"

    def _tighten_splitters(self, control):
        """Shrink the Installed Packages HSplit divider and zero the pane inner
        margins so the collapse button sits flush with an even, minimal gap on
        both sides."""
        if control is None:
            return
        for splitter in control.findChildren(QSplitter):
            splitter.setHandleWidth(INSTALLED_SPLIT_GAP)
            for i in range(splitter.count()):
                pane = splitter.widget(i)
                for widget in [pane, *pane.findChildren(QWidget)]:
                    layout = widget.layout()
                    if layout is not None:
                        layout.setContentsMargins(0, 0, 0, 0)
                        layout.setSpacing(INSTALLED_SPLIT_GAP)

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
    @observe("model:installed_rows:items:open_docs")
    def _on_open_docs(self, event):
        row = event.object
        if row.doc_url:
            webbrowser.open(row.doc_url)

    @observe("model:installed_rows:items:version")
    def _on_version_selected(self, event):
        if self._suppress_version:
            return
        row = event.object
        new_version, old_version = event.new, event.old
        if not new_version or new_version == old_version:
            return
        # This fires from inside the cell editor's commit; running a modal
        # confirm (nested event loop) + reverting the trait here reentrantly
        # corrupts the item-view mid-edit and crashes Qt. Handle it after the
        # editor has closed.
        QTimer.singleShot(
            0, lambda: self._prompt_install_version(row, new_version, old_version))

    def _prompt_install_version(self, row, new_version, old_version):
        if confirm(parent=None, title="Install version?",
                   message=f"Install <b>{_esc(row.label)}</b> version "
                           f"<b>{_esc(new_version)}</b>? This changes the package "
                           f"in the environment.", cancel=False) != YES:
            self._set_row_version(row, old_version)  # revert the dropdown
            return
        label, dist = row.label, row.dist_name
        self._run(lambda: self.model.do_install_version(dist, new_version),
                  title="Installing version",
                  message=f"Installing {label} {new_version}…",
                  done=lambda r: (self.model.refresh_installed(),
                                  self._after_change(
                                      f"Installed <b>{_esc(label)}</b> "
                                      f"{_esc(new_version)}.")))

    @observe("model:installed_rows:items:upgrade")
    def _on_upgrade(self, event):
        row = event.object
        latest = row.available_versions[0] if row.available_versions else ""
        label, dist = row.label, row.dist_name
        target = f" (<b>{_esc(latest)}</b>)" if latest else ""
        if confirm(parent=None, title="Upgrade plugin?",
                   message=f"Upgrade <b>{_esc(label)}</b> to the latest "
                           f"version{target}?", cancel=False) != YES:
            return
        self._run(lambda: self.model.do_upgrade(dist),
                  title="Upgrading plugin", message=f"Upgrading {label}…",
                  done=lambda r: (self.model.refresh_installed(),
                                  self._after_change(
                                      f"Upgraded <b>{_esc(label)}</b>.")))

    @observe("model:installed_rows:items:uninstall")
    def _on_uninstall(self, event):
        row = event.object
        label, dist, manifest = row.label, row.dist_name, row.manifest_name
        if confirm(parent=None, title="Uninstall Plugin?",
                   message=f"Uninstall <b>{_esc(label)}</b>? This removes its "
                           f"package from the environment.", cancel=False) != YES:
            return
        self.model.pre_uninstall(manifest)
        self._run(lambda: self.model.do_uninstall(dist),
                  title="Uninstalling plugin", message=f"Removing {label}…",
                  done=lambda r: (self.model.refresh_installed(),
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
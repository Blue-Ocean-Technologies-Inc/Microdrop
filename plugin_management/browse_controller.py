"""Handler for the Browse Plugins window: fetch the channel list on open and
install the selected package. The selected row's details fill automatically
(the model observes ``selected``). The model holds state/logic; this holds the
flow (dialogs, worker-thread progress).

Worker callables (fetch_data / do_install) must not touch model traits — they
return data and the GUI-thread callbacks apply it (model is mutated on the GUI
thread only)."""
from traits.api import Instance
from pyface.tasks.api import Task
from pyface.qt.QtWidgets import QToolBar
from pyface.qt.QtGui import QFont

from microdrop_application.dialogs.pyface_wrapper import (
    confirm, information, error as error_dialog, YES, escape_html_multiline)
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_utils.threaded_progress import run_with_wait
from microdrop_utils.traitsui_qt_helpers import SafeCancelTableHandler

from plugin_management.hot_load import hot_load_installed
from plugin_management.i_plugin_group_manager import IPluginGroupManager
from plugin_management.relaunch import finish_change

#: Point size of the Material Symbols glyph rendered on the Refresh toolbar button.
REFRESH_ICON_POINT_SIZE = 16


def _consent_html(pkg):
    name = escape_html_multiline(pkg.name)
    deps = ", ".join(escape_html_multiline(d) for d in pkg.raw.get("depends", [])) or "none"
    return (f"<b>{name}</b> (v{escape_html_multiline(pkg.version)})<br><br>"
            f"Dependencies: {deps}<br><br>"
            f"<b>Warning:</b> installing runs third-party code that has not been "
            f"verified. Only install plugins you trust.<br><br>Install this plugin?")


class BrowsePluginsHandler(SafeCancelTableHandler):
    """Fetches the channel list and installs the selected package."""

    task = Instance(Task)

    def init(self, info):
        super().init(info)            # Escape deselects instead of closing
        self._style_toolbar(info)
        self._load(info.object, message="Fetching available plugins…")
        return True

    def _style_toolbar(self, info):
        """Render the Refresh toolbar action as a Material Symbols glyph by
        giving the toolbar the icon font (its only action's label is the glyph)."""
        control = getattr(info.ui, "control", None)
        if control is None:
            return
        for toolbar in control.findChildren(QToolBar):
            toolbar.setFont(QFont(ICON_FONT_FAMILY, REFRESH_ICON_POINT_SIZE))

    def refresh(self, info):
        """Re-fetch the available-plugins list from the channel (the repo)."""
        self._load(info.object, message="Refreshing plugin list…")

    def _load(self, model, *, message):
        """Run the channel fetch on a worker, applying the result on the GUI
        thread. Shared by the initial open and the Refresh button."""
        run_with_wait(
            model.fetch_data,
            title="Loading plugins", message=message,
            on_success=lambda result: self._after_fetch(model, result),
            on_error=lambda e: error_dialog(
                parent=None, title="Could not load plugins", message=str(e)))

    def _after_fetch(self, model, result):
        data, stale = result
        model.set_packages(data, stale)        # GUI thread
        if stale:
            information(parent=None, title="Offline",
                        message="Could not reach the plugin channel — showing the "
                                "last cached list.")

    def install_selected(self, info):
        model = info.object
        pkg = model.selected
        if pkg is None:
            information(parent=None, title="No selection",
                        message="Select a plugin to install.")
            return
        if confirm(parent=None, title="Install Plugin?",
                   message=_consent_html(pkg), cancel=False) != YES:
            return
        run_with_wait(
            lambda: model.do_install(pkg.name, pkg.version),
            title="Installing plugin",
            message=f"Installing {pkg.name} {pkg.version}…",
            on_success=lambda r: self._finish_install(pkg, r),
            on_error=lambda e: error_dialog(
                parent=None, title="Install failed", message=str(e)))

    def _finish_install(self, pkg, result):
        """GUI thread: try to apply the install live, then report."""
        ok = self._hot_load(pkg.name, result)
        name = escape_html_multiline(pkg.name)
        version = escape_html_multiline(pkg.version)
        verb = "Installed and enabled" if ok else "Installed"
        finish_change(self.task, f"{verb} <b>{name}</b> {version}.", ok)

    def _hot_load(self, dist_name, result):
        """False (relaunch) whenever the live application or its group manager
        is unreachable — e.g. the standalone installer demo."""
        application = getattr(
            getattr(self.task, "window", None), "application", None)
        if application is None:
            return False
        manager = application.get_service(IPluginGroupManager)
        if manager is None:
            return False
        return hot_load_installed(application, manager, dist_name, result.diff)

    def do_close(self, info):
        info.ui.dispose()

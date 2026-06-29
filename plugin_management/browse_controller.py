"""Handler for the Browse Plugins window: fetch the channel list on open and
install the selected package. The selected row's details fill automatically
(the model observes ``selected``). The model holds state/logic; this holds the
flow (dialogs, worker-thread progress).

Worker callables (fetch_data / do_install) must not touch model traits — they
return data and the GUI-thread callbacks apply it (model is mutated on the GUI
thread only)."""
from traits.api import Instance
from pyface.tasks.api import Task

from microdrop_application.dialogs.pyface_wrapper import (
    confirm, information, error as error_dialog, YES, escape_html_multiline)
from microdrop_utils.threaded_progress import run_with_wait
from microdrop_utils.traitsui_qt_helpers import SafeCancelTableHandler

from plugin_management.relaunch import confirm_and_relaunch


def _consent_html(pkg):
    name = escape_html_multiline(pkg.name)
    deps = ", ".join(escape_html_multiline(d) for d in pkg.raw.get("depends", [])) or "none"
    return (f"<b>{name}</b> (v{escape_html_multiline(pkg.version)})<br><br>"
            f"Dependencies pixi will install: {deps}<br><br>"
            f"<b>Warning:</b> installing runs third-party code that has not been "
            f"verified. Only install plugins you trust.<br><br>Install this plugin?")


class BrowsePluginsHandler(SafeCancelTableHandler):
    """Fetches the channel list and installs the selected package."""

    task = Instance(Task)

    def init(self, info):
        super().init(info)            # Escape deselects instead of closing
        self._load(info.object, message="Fetching available plugins…")
        return True

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
            lambda: model.do_install(pkg.name),
            title="Installing plugin", message=f"Installing {pkg.name}…",
            on_success=lambda r: confirm_and_relaunch(
                self.task, f"Installed <b>{escape_html_multiline(pkg.name)}</b>."),
            on_error=lambda e: error_dialog(
                parent=None, title="Install failed", message=str(e)))

    def do_close(self, info):
        info.ui.dispose()

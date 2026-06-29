"""Handler for the Manage Plugins window: the action-button handlers + the UI
glue (dialogs, worker-thread progress, relaunch). The model holds state/logic;
this holds the flow. In each handler, ``info.object`` is the model."""
from traits.api import Instance, Enum, HasTraits
from traitsui.api import EnumEditor, Item, View
from pyface.tasks.api import Task

from microdrop_application.dialogs.pyface_wrapper import (
    confirm, error as error_dialog, YES, information, escape_html_multiline)

from microdrop_utils.threaded_progress import run_with_wait

from logger.logger_service import get_logger
from microdrop_utils.traitsui_qt_helpers import SafeCancelTableHandler

from plugin_management.browse_model import BrowsePluginsModel
from plugin_management.browse_view import browse_view
from plugin_management.browse_controller import BrowsePluginsHandler
from plugin_management.relaunch import confirm_and_relaunch

logger = get_logger(__name__)


def _esc(s):
    return escape_html_multiline(str(s))


class PluginManagerHandler(SafeCancelTableHandler):
    """Handles the Manage Plugins view's actions over the model (info.object)."""

    task = Instance(Task)

    # --- Apply: live hot-load, no relaunch ---
    def apply_changes(self, info):
        try:
            info.object.apply(self.task)
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

    # --- Uninstall: pick installed -> confirm -> pre_uninstall -> threaded remove ---
    def uninstall_plugin(self, info):
        model = info.object
        installed = model.installed_plugins()
        if not installed:
            information(parent=None, title="Uninstall Plugin",
                       message="No installed plugin packages to uninstall.")
            return
        choice = self._pick_installed(installed)
        if choice is None:
            return
        manifest_name, label, dist_name, _groups = choice
        if confirm(parent=None, title="Uninstall Plugin?",
                   message=f"Uninstall <b>{_esc(label)}</b>? This removes its "
                           f"package from the environment.", cancel=False) != YES:
            return
        model.pre_uninstall(self.task, manifest_name)
        self._run(lambda: model.do_uninstall(dist_name),
                  title="Uninstalling plugin", message=f"Removing {label}…",
                  done=lambda r: (model.refresh(),
                                  self._after_change(
                                      f"Uninstalled <b>{_esc(label)}</b>.")))

    # --- helpers ---
    def _run(self, work, *, title, message, done):
        run_with_wait(work, title=title, message=message, on_success=done,
                      on_error=lambda e: error_dialog(
                          parent=None, title=title, message=str(e)))

    def _after_change(self, msg_html):
        confirm_and_relaunch(self.task, msg_html)

    def _pick_installed(self, installed):
        """Single-select picker; returns the chosen installed-plugin tuple or None."""
        by_label = {label: (m, label, d, g) for (m, label, d, g) in installed}
        choices = list(by_label)

        class _Pick(HasTraits):
            choice = Enum(choices)

        picker = _Pick()
        ui = picker.edit_traits(view=View(
            Item("choice", editor=EnumEditor(values=choices), label="Plugin"),
            buttons=["OK", "Cancel"], kind="livemodal",
            title="Uninstall which plugin?"))
        return by_label[picker.choice] if ui.result else None

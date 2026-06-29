"""Handler for the Manage Plugins window: the action-button handlers + the UI
glue (dialogs, worker-thread progress, relaunch). The model holds state/logic;
this holds the flow. In each handler, ``info.object`` is the model."""
from traits.api import Instance
from traitsui.api import Handler
from pyface.tasks.api import Task

from microdrop_utils.threaded_progress import run_with_wait
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _esc(s):
    from microdrop_application.dialogs.pyface_wrapper import escape_html_multiline
    return escape_html_multiline(str(s))


class PluginManagerController(Handler):
    """Handles the Manage Plugins view's actions over the model (info.object)."""

    task = Instance(Task)

    # --- Apply: live hot-load, no relaunch ---
    def apply_changes(self, info):
        from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
        try:
            info.object.apply(self.task)
            info.object.refresh()
        except Exception as e:
            logger.exception("apply enable/disable failed")
            error_dialog(parent=None, title="Apply failed", message=str(e))

    def do_close(self, info):
        info.ui.dispose()

    # --- Install: pick .conda -> preview -> threaded install -> relaunch ---
    def install_plugin(self, info):
        from microdrop_application.dialogs.pyface_wrapper import (
            file_dialog, confirm, error as error_dialog, YES)
        model = info.object
        path = file_dialog(parent=None, action="open",
                           wildcard="MicroDrop plugin package (*.conda)|*.conda")
        if not path:
            return
        try:
            preview = model.preview(path)
        except Exception as e:
            error_dialog(parent=None, title="Install failed", message=str(e))
            return
        if confirm(parent=None, title="Install Plugin?",
                   message=self._consent_html(preview), cancel=False) != YES:
            return
        self._run(lambda: model.do_install(path),
                  title="Installing plugin", message=f"Installing {preview.name}…",
                  done=lambda r: self._after_change(
                      f"Installed <b>{_esc(preview.name)}</b>."))

    # --- Uninstall: pick installed -> confirm -> pre_uninstall -> threaded remove ---
    def uninstall_plugin(self, info):
        from microdrop_application.dialogs.pyface_wrapper import (
            confirm, information, YES)
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
        from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
        run_with_wait(work, title=title, message=message, on_success=done,
                      on_error=lambda e: error_dialog(
                          parent=None, title=title, message=str(e)))

    def _after_change(self, msg_html):
        from microdrop_application.dialogs.pyface_wrapper import confirm, information, YES
        if confirm(parent=None, title="Relaunch required",
                   message=f"{msg_html}<br><br>Relaunch MicroDrop now to apply?",
                   cancel=False) == YES:
            from plugin_management.relaunch import relaunch_app
            relaunch_app(self.task.window.application)
        else:
            information(parent=None, title="Relaunch later",
                        message="The change takes effect the next time you launch "
                                "MicroDrop.")

    def _consent_html(self, preview):
        deps = ", ".join(_esc(d) for d in preview.depends) or "none"
        groups = "(manifest unreadable)"
        if preview.manifest is not None:
            blocks = []
            for g in preview.manifest.groups:
                plugins = "<br>".join(f"&nbsp;&nbsp;{_esc(p)}" for p in g.plugins)
                blocks.append(f"<b>{_esc(g.label)}</b><br>{plugins}")
            groups = "<br>".join(blocks)
        return (f"<b>{_esc(preview.name)}</b> (v{_esc(preview.version)})<br><br>"
                f"Dependencies pixi will install: {deps}<br><br>"
                f"Plugin groups provided:<br>{groups}<br><br>"
                f"<b>Warning:</b> installing runs third-party code that has not been "
                f"verified. Only install plugins you trust.<br><br>Install this plugin?")

    def _pick_installed(self, installed):
        """Single-select picker; returns the chosen installed-plugin tuple or None."""
        from traits.api import Enum, HasTraits
        from traitsui.api import EnumEditor, Item, View
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

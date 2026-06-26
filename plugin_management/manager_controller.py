"""TraitsUI Controller for the Manage Plugins window: wires the view's actions to
the model and owns the UI glue (dialogs, worker-thread + please-wait modal,
relaunch). The model holds the state/business logic; this holds the flow."""
from traitsui.api import Controller

from microdrop_utils.threaded_progress import run_with_wait
from plugin_management.manager_view import manager_view
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _esc(s):
    from microdrop_application.dialogs.pyface_wrapper import escape_html_multiline
    return escape_html_multiline(str(s))


class PluginManagerController(Controller):
    """Pairs PluginManagerModel with the Manage Plugins view."""

    def __init__(self, model, task, **traits):
        super().__init__(model=model, **traits)
        self.task = task

    def trait_view(self, name=None, view_element=None):
        return manager_view()

    # --- Apply: live hot-load, no relaunch ---------------------------
    def apply_changes(self, info):
        from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
        try:
            self.model.apply(self.task)
            self.model.refresh()
        except Exception as e:
            logger.exception("apply enable/disable failed")
            error_dialog(parent=None, title="Apply failed", message=str(e))

    def close(self, info, is_ok=None):
        info.ui.dispose()
        return True

    # --- Install: pick .conda -> preview -> threaded install -> relaunch
    def install_plugin(self, info):
        from microdrop_application.dialogs.pyface_wrapper import (
            file_dialog, confirm, error as error_dialog, YES)
        path = file_dialog(parent=None, action="open",
                           wildcard="MicroDrop plugin package (*.conda)|*.conda")
        if not path:
            return
        try:
            preview = self.model.preview(path)
        except Exception as e:
            error_dialog(parent=None, title="Install failed", message=str(e))
            return
        if confirm(parent=None, title="Install Plugin?",
                   message=self._consent_html(preview), cancel=False) != YES:
            return
        self._run(lambda: self.model.do_install(path),
                  title="Installing plugin",
                  message=f"Installing {preview.name}…",
                  done=lambda r: self._after_change(
                      f"Installed <b>{_esc(preview.name)}</b>."))

    # --- Uninstall: pick installed -> confirm -> pre_uninstall -> threaded remove -> relaunch
    def uninstall_plugin(self, info):
        from microdrop_application.dialogs.pyface_wrapper import (
            confirm, information, error as error_dialog, YES)
        rows = self.model.installed_rows()
        if not rows:
            information(parent=None, title="Uninstall Plugin",
                       message="No installed plugin packages to uninstall.")
            return
        row = self._pick_installed(rows)
        if row is None:
            return
        label = row.label
        if confirm(parent=None, title="Uninstall Plugin?",
                   message=f"Uninstall <b>{_esc(label)}</b>? This removes its "
                           f"package from the environment.", cancel=False) != YES:
            return
        self.model.pre_uninstall(self.task, row.manifest_name)
        self._run(lambda: self.model.do_uninstall(row.dist_name),
                  title="Uninstalling plugin", message=f"Removing {label}…",
                  done=lambda r: (self.model.refresh(),
                                  self._after_change(
                                      f"Uninstalled <b>{_esc(label)}</b>.")))

    # --- helpers -----------------------------------------------------
    def _run(self, work, *, title, message, done):
        from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
        run_with_wait(
            work, title=title, message=message,
            on_success=done,
            on_error=lambda e: error_dialog(parent=None, title=title, message=str(e)),
        )

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
            rows = []
            for g in preview.manifest.groups:
                plugins = "<br>".join(f"&nbsp;&nbsp;{_esc(p)}" for p in g.plugins)
                rows.append(f"<b>{_esc(g.label)}</b><br>{plugins}")
            groups = "<br>".join(rows)
        return (
            f"<b>{_esc(preview.name)}</b> (v{_esc(preview.version)})<br><br>"
            f"Dependencies pixi will install: {deps}<br><br>"
            f"Plugin groups provided:<br>{groups}<br><br>"
            f"<b>Warning:</b> installing runs third-party code that has not been "
            f"verified. Only install plugins you trust.<br><br>Install this plugin?"
        )

    def _pick_installed(self, rows):
        """Small single-select picker; returns the chosen PluginRow or None."""
        from traits.api import Enum, HasTraits
        from traitsui.api import EnumEditor, Item, View
        by_label = {f"{r.label}  (v{r.version})": r for r in rows}
        choices = list(by_label)

        class _Pick(HasTraits):
            choice = Enum(choices)
        picker = _Pick()
        ui = picker.edit_traits(view=View(
            Item("choice", editor=EnumEditor(values=choices),
                 label="Plugin"),
            buttons=["OK", "Cancel"], kind="livemodal",
            title="Uninstall which plugin?"))
        return by_label[picker.choice] if ui.result else None

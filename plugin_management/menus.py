"""Tools-menu actions for plugin management — Install, Uninstall, Manage.

Contributed to the microdrop task's MenuBar/Tools by PluginManagementPlugin via
TASK_EXTENSIONS. Each is a TaskAction so ``self.task`` is populated; heavy
imports are deferred into ``perform`` so loading this module stays light."""

from pyface.tasks.action.api import TaskAction

from logger.logger_service import get_logger

logger = get_logger(__name__)


class ManagePluginsAction(TaskAction):
    """Open the Manage Plugins dialog — a checkbox per registered plugin group
    (bundled + installed). Applies the selection on OK via
    PluginGroupManager.apply."""

    id = "manage_plugins_action"
    name = "&Manage Plugins…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Manage Plugins: no task available")
            return
        from plugin_management.i_plugin_group_manager import IPluginGroupManager
        from plugin_management.manage_dialog import PluginsManagerModel

        manager = task.window.application.get_service(IPluginGroupManager)
        if manager is None:
            logger.error("Manage Plugins: PluginGroupManager service not found")
            return

        groups = [
            (name, group.label or name, group.loaded)
            for name, group in manager.groups.items()
        ]
        model = PluginsManagerModel(groups)
        ui = model.edit_traits(kind="livemodal")
        if not ui.result:                       # Cancel / closed -> no change
            return
        try:
            manager.apply(task, model.desired())
        except Exception:
            logger.exception("Manage Plugins: applying group changes failed")


class InstallPluginAction(TaskAction):
    """Pick a built plugin package (.conda) and install it via pixi. Shows an
    informed-consent dialog, then `pixi add`s the package (the solver resolves
    its dependencies) and offers a relaunch."""

    id = "install_plugin_action"
    name = "&Install Plugin…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Install Plugin: no task available")
            return
        from microdrop_application.dialogs.pyface_wrapper import (
            file_dialog, confirm, information, error as error_dialog, YES,
            escape_html_multiline,
        )
        from plugin_management import package_installer

        path = file_dialog(
            parent=None, action="open",
            wildcard="MicroDrop plugin package (*.conda)|*.conda",
        )
        if not path:
            return

        def _consent(name):
            safe = escape_html_multiline(name)
            body = (
                f"Install the plugin package <b>{safe}</b>?<br><br>"
                f"pixi will install it and resolve its dependencies into the "
                f"environment.<br><br>"
                f"<b>Warning:</b> installing runs third-party code that has not "
                f"been verified. Only install plugins you trust."
            )
            return confirm(parent=None, message=body,
                           title="Install Plugin?", cancel=False) == YES

        try:
            result = package_installer.install_conda_file(path, confirm=_consent)
        except package_installer.InstallCancelled:
            return
        except Exception as e:
            error_dialog(parent=None, title="Install failed", message=str(e))
            return

        safe = escape_html_multiline(result.name)
        if confirm(parent=None, title="Relaunch required",
                   message=f"Installed <b>{safe}</b>.<br><br>Its packages become "
                           f"available after a relaunch.<br><br>"
                           f"Relaunch MicroDrop now?",
                   cancel=False) == YES:
            from plugin_management.relaunch import relaunch_into_plugins_env
            relaunch_into_plugins_env(task.window.application)
        else:
            information(parent=None, title="Relaunch later",
                       message=f"<b>{safe}</b> will be available the next time "
                               f"you launch MicroDrop.")


class UninstallPluginAction(TaskAction):
    """Uninstall a user-installed plugin package (auto-disable its loaded
    groups, then `pixi remove`). Bundled plugins are not listed."""

    id = "uninstall_plugin_action"
    name = "&Uninstall Plugin…"

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Uninstall Plugin: no task available")
            return
        from microdrop_application.dialogs.pyface_wrapper import (
            confirm, information, error as error_dialog, YES, escape_html_multiline,
        )
        from plugin_management.i_plugin_group_manager import IPluginGroupManager
        from plugin_management import package_installer
        from plugin_management.uninstall_dialog import UninstallPluginModel

        manager = task.window.application.get_service(IPluginGroupManager)
        if manager is None:
            logger.error("Uninstall Plugin: PluginGroupManager service not found")
            return

        installed = manager.installed_plugins()
        if not installed:
            information(parent=None, title="Uninstall Plugin",
                       message="No installed plugin packages to uninstall.")
            return

        model = UninstallPluginModel(installed)
        ui = model.edit_traits(kind="livemodal")
        if not ui.result:
            return
        name = model.selected
        label = {n: l for n, l, _d, _g in installed}.get(name, name)
        groups = {n: g for n, _l, _d, g in installed}.get(name, [])
        safe_label = escape_html_multiline(label)
        if confirm(parent=None,
                   message=f"Uninstall <b>{safe_label}</b>?<br><br>"
                           f"This removes its package from the environment.",
                   title="Uninstall Plugin?", cancel=False) != YES:
            return
        try:
            for group_name in groups:
                if manager.is_loaded(group_name):
                    manager.disable(task, group_name)
            manager.deregister_plugin(name)
            package_installer.uninstall_package(name)
        except Exception as e:
            error_dialog(parent=None, title="Uninstall failed", message=str(e))
            return
        if confirm(parent=None, title="Relaunch required",
                   message=f"Uninstalled <b>{safe_label}</b>.<br><br>Relaunch "
                           f"MicroDrop now to finish removing it?",
                   cancel=False) == YES:
            from plugin_management.relaunch import relaunch_into_plugins_env
            relaunch_into_plugins_env(task.window.application)
        else:
            information(parent=None, title="Relaunch later",
                       message=f"<b>{safe_label}</b> has been uninstalled and will "
                               f"be fully removed after a relaunch.")

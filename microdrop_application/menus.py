from pyface.action.api import Action
from pyface.tasks.action.api import TaskAction

from microdrop_application.consts import ADVANCED_MODE_CHANGE
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger
logger = get_logger(__name__)

_advanced_mode_enabled = False

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()


def is_advanced_mode():
    return app_globals.get("microdrop.advanced_mode", False)



class AdvancedModeAction(Action):
    id = "advanced_mode_action"
    name = "&Advanced Mode"
    style = "toggle"
    checked = is_advanced_mode()

    def perform(self, event):

        app_globals["microdrop.advanced_mode"] = self.checked
        logger.critical("Microdrop Running in Advanced Mode!" if self.checked else "Microdrop Advanced Mode is Off.")

        publish_message(
            topic=ADVANCED_MODE_CHANGE,
            message=str(self.checked),
        )


class ManagePluginsAction(TaskAction):
    """Tools-menu action opening the Manage Plugins dialog — a checkbox per
    registered optional plugin group (bundled + installed). Applies the
    selection on OK via PluginGroupManager.apply. TaskAction so self.task is
    populated; lives in the always-loaded task."""

    id = "manage_plugins_action"
    name = "&Manage Plugins…"

    def perform(self, event):
        task = event.task
        if task is None:
            logger.error("Manage Plugins: no task available")
            return
        from microdrop_application.plugin_group_manager import PluginGroupManager
        from microdrop_application.plugins_manager_dialog import PluginsManagerModel

        manager = task.window.application.get_service(PluginGroupManager)
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
    """Tools-menu action: pick a .microdrop_plugin archive and install it.
    Shows an informed-consent dialog (what will be installed + a third-party
    code warning) before extracting, then registers its groups live."""

    id = "install_plugin_action"
    name = "&Install Plugin…"

    def perform(self, event):
        task = event.task
        if task is None:
            logger.error("Install Plugin: no task available")
            return
        from microdrop_application.dialogs.pyface_wrapper import (
            file_dialog, confirm, information, error as error_dialog, YES,
            escape_html_multiline,
        )
        from microdrop_application.plugin_group_manager import PluginGroupManager
        from microdrop_application.plugins import installer

        path = file_dialog(
            parent=None, action="open",
            wildcard="MicroDrop plugin (*.microdrop_plugin)|*.microdrop_plugin",
        )
        if not path:
            return

        manager = task.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.error("Install Plugin: PluginGroupManager service not found")
            return

        def _consent(manifest):
            classes = "<br>".join(
                f"&nbsp;&nbsp;{escape_html_multiline(p)}"
                for g in manifest.groups for p in g.plugins
            )
            pkgs = ", ".join(escape_html_multiline(p) for p in manifest.packages)
            label = escape_html_multiline(manifest.label)
            version = escape_html_multiline(manifest.version or "?")
            body = (
                f"<b>{label}</b> (v{version})<br><br>"
                f"Packages: {pkgs}<br>"
                f"Plugin classes that will become importable:<br>{classes}<br><br>"
                f"<b>Warning:</b> installing runs third-party code that has not "
                f"been verified. Only install plugins you trust.<br><br>"
                f"Install this plugin?"
            )
            return confirm(parent=None, message=body,
                           title="Install Plugin?", cancel=False) == YES

        try:
            manifest = installer.install_from_zip(path, manager, confirm=_consent)
        except installer.InstallCancelled:
            return
        except Exception as e:
            error_dialog(parent=None, title="Install failed", message=str(e))
            return

        information(
            parent=None, title="Plugin installed",
            message=f"Installed <b>{manifest.label}</b>.<br><br>"
                    f"Enable it from Tools → Manage Plugins.",
        )


class UninstallPluginAction(TaskAction):
    """Tools-menu action: remove a user-installed plugin (its files, groups,
    modules, and enabled flags), auto-disabling any loaded group first. Bundled
    plugins are not listed."""

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
        from microdrop_application.plugin_group_manager import PluginGroupManager
        from microdrop_application.plugins import installer
        from microdrop_application.plugins_uninstall_dialog import UninstallPluginModel

        manager = task.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.error("Uninstall Plugin: PluginGroupManager service not found")
            return

        installed = manager.installed_plugins()
        if not installed:
            information(parent=None, title="Uninstall Plugin",
                       message="No user-installed plugins to uninstall.")
            return

        model = UninstallPluginModel(installed)
        ui = model.edit_traits(kind="livemodal")
        if not ui.result:
            return
        name = model.selected
        label = {n: l for n, l, _d, _g in installed}.get(name, name)
        safe_label = escape_html_multiline(label)
        if confirm(parent=None,
                   message=f"Uninstall <b>{safe_label}</b>?<br><br>"
                           f"This deletes its installed files.",
                   title="Uninstall Plugin?", cancel=False) != YES:
            return
        try:
            installer.uninstall_plugin(task, manager, name)
        except Exception as e:
            error_dialog(parent=None, title="Uninstall failed", message=str(e))
            return
        information(parent=None, title="Plugin uninstalled",
                   message=f"Uninstalled <b>{safe_label}</b>.")
from pyface.action.api import Action
from pyface.tasks.action.api import TaskAction

from microdrop_application.consts import (
    ADVANCED_MODE_CHANGE, MAGNET_BACKEND_GROUP, MAGNET_UI_GROUP,
    PERIPHERAL_BACKEND_ENABLED_KEY, PERIPHERAL_UI_ENABLED_KEY,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger
logger = get_logger(__name__)

_advanced_mode_enabled = False

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()


def is_advanced_mode():
    return app_globals.get("microdrop.advanced_mode", False)


def is_peripheral_ui_enabled():
    return app_globals.get(PERIPHERAL_UI_ENABLED_KEY, False)


def is_peripheral_backend_enabled():
    return app_globals.get(PERIPHERAL_BACKEND_ENABLED_KEY, False)


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


class ManagePeripheralsAction(TaskAction):
    """Tools-menu action opening the Manage Peripherals dialog, which hot
    loads/unloads the magnet UI and backend plugin groups independently.
    TaskAction (not plain Action) so ``self.task`` is populated — the
    orchestrator needs the live task/window/application. Lives in the
    always-loaded task so the entry is present even when both groups are
    unloaded."""

    id = "manage_peripherals_action"
    name = "&Manage Peripherals…"

    def perform(self, event=None):
        # Local imports avoid pulling the orchestrator (and its Qt helper) and
        # the dialog in at menu-import time, and sidestep import cycles.
        from microdrop_application.plugin_group_manager import PluginGroupManager
        from microdrop_application.peripherals_manager_dialog import (
            PeripheralsManagerModel,
        )

        manager = event.task.window.application.get_service(PluginGroupManager)
        if manager is None:
            logger.error("Manage Peripherals: PluginGroupManager service not found")
            return

        model = PeripheralsManagerModel(
            magnet_ui_enabled=manager.is_loaded(MAGNET_UI_GROUP),
            magnet_backend_enabled=manager.is_loaded(MAGNET_BACKEND_GROUP),
        )
        ui = model.edit_traits(kind="livemodal")
        if not ui.result:     # Cancel / closed -> no change
            return

        manager.apply(event.task, {
            MAGNET_UI_GROUP: model.magnet_ui_enabled,
            MAGNET_BACKEND_GROUP: model.magnet_backend_enabled,
        })
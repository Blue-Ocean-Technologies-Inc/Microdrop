from pyface.action.api import Action
from pyface.tasks.action.api import TaskAction

from microdrop_application.consts import (
    ADVANCED_MODE_CHANGE, MAGNET_PERIPHERALS_GROUP, PERIPHERALS_ENABLED_KEY,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger
logger = get_logger(__name__)

_advanced_mode_enabled = False

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()


def is_advanced_mode():
    return app_globals.get("microdrop.advanced_mode", False)


def is_peripherals_enabled():
    return app_globals.get(PERIPHERALS_ENABLED_KEY, False)


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


class PeripheralsToggleAction(TaskAction):
    """Tools-menu toggle that hot loads/unloads the optional magnet-peripheral
    plugin group (controller + protocol column + dock pane) at runtime, no
    restart. TaskAction (not plain Action) so ``self.task`` is populated — the
    orchestrator needs the live task/window/application. Lives in the
    always-loaded task, so the toggle is present even when the group is
    unloaded."""

    id = "peripherals_toggle_action"
    name = "&Peripherals (Magnet)"
    style = "toggle"
    checked = is_peripherals_enabled()

    def perform(self, event):
        task = self.task
        if task is None:
            logger.error("Peripherals toggle: no task available")
            return
        # Local import avoids pulling the orchestrator (and its Qt helper) in
        # at menu-import time, and sidesteps any import cycle.
        from microdrop_application.plugin_group_manager import PluginGroupManager

        application = task.window.application
        manager = application.get_service(PluginGroupManager)
        if manager is None:
            logger.error("Peripherals toggle: PluginGroupManager service not found")
            self.checked = not self.checked     # revert — nothing happened
            return

        try:
            if self.checked:
                manager.enable(task, MAGNET_PERIPHERALS_GROUP)
            else:
                manager.disable(task, MAGNET_PERIPHERALS_GROUP)
        except Exception:
            logger.exception("Peripherals toggle failed; reverting checkmark")
            self.checked = not self.checked

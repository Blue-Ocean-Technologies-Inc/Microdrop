from pyface.action.api import Action

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

        publish_message.send(
            topic=ADVANCED_MODE_CHANGE,
            message=str(self.checked),
        )

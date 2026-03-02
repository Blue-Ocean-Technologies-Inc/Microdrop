from pyface.action.api import Action

from microdrop_application.consts import ADVANCED_MODE_CHANGE
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger
logger = get_logger(__name__)

class AdvancedModeAction(Action):
    id = "advanced_mode_action"
    name = "&Advanced Mode"
    style = "toggle"
    checked = False

    def perform(self, event):

        logger.critical("Microdrop Running in Advanced Mode!" if self.checked else "Microdrop Advanced Mode is Off.")

        publish_message.send(
            topic=ADVANCED_MODE_CHANGE,
            message=str(self.checked),
        )

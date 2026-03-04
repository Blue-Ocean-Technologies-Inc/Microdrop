from envisage.api import Plugin, SERVICE_OFFERS
from traits.api import List

from dropbot_controller.consts import DROPBOT_DISCONNECTED
from logger.logger_service import get_logger
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT

logger = get_logger(__name__)

class PortDropbotControllerPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # this plugin contributes some service offers
    service_offers = List(contributes_to=SERVICE_OFFERS)

    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)


    def start(self):
        """Initialize the dropbot on plugin start"""

        from .manager import ConnectionManager
        self.dropbot_controller = ConnectionManager(app_preferences=self.application.preferences)

    def stop(self):
        """Cleanup when the plugin is stopped."""
        if hasattr(self, "dropbot_controller"):
            mc = self.dropbot_controller
            mc._shutting_down = True
            if hasattr(mc, "monitor_scheduler") and mc.monitor_scheduler is not None:
                try:
                    mc.monitor_scheduler.shutdown(wait=False)
                except Exception as e:
                    logger.warning(f"Monitor scheduler shutdown: {e}")
                mc.monitor_scheduler = None
            if mc.connected:
                mc.connected = False
                publish_message("", DROPBOT_DISCONNECTED)
            mc.driver.close()
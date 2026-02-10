from envisage.api import Plugin, SERVICE_OFFERS
from traits.api import List
# microdrop imports
from logger.logger_service import get_logger
from message_router.consts import ACTOR_TOPIC_ROUTES

# Initialize logger
logger = get_logger(__name__)

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT

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
            self.dropbot_controller.driver.close()
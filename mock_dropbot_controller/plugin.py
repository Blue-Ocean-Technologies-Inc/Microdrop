from envisage.plugin import Plugin
from traits.api import List

from message_router.consts import ACTOR_TOPIC_ROUTES
from logger.logger_service import get_logger

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name, DROPBOT_CONNECTED, CHIP_INSERTED
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

logger = get_logger(__name__)


class MockDropbotControllerPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def start(self):
        from .mock_controller import MockDropbotController

        self.mock_controller = MockDropbotController()
        self.mock_controller.connected = True

        # Publish connected signal so the UI picks it up
        publish_message(topic=DROPBOT_CONNECTED, message="mock_dropbot")
        publish_message(topic=CHIP_INSERTED, message="True")
        self.mock_controller.chip_inserted = True

        logger.info("MockDropbotControllerPlugin started — mock device connected with chip")

    def stop(self):
        if hasattr(self, 'mock_controller'):
            self.mock_controller.cleanup()
            logger.info("MockDropbotControllerPlugin stopped")

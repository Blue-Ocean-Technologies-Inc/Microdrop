# sys imports
import os
import sys
import time

# enthought imports
from envisage.api import CorePlugin, Plugin, SERVICE_OFFERS, ServiceOffer
from envisage.application import Application
from traits.api import provides, HasTraits, List, observe, Str

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# plugin imports
from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from dropbot_controller.plugin import DropbotControllerPlugin
from dropbot_controller.consts import START_DEVICE_MONITORING
from message_router.plugin import MessageRouterPlugin
from message_router.consts import ACTOR_TOPIC_ROUTES

# local helpers imports
from microdrop_utils.broker_server_helpers import dramatiq_workers_context, redis_server_context
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


@provides(IDropbotControlMixinService)
class DropbotDummyMixinService(HasTraits):
    """
    A mixin Class that adds methods to monitor a dropbot connection and get some dropbot information.
    """

    id = Str('dummy_dropbot_control')
    name = Str('Dummy Dropbot Control')

    ######################################## Methods to Expose #############################################
    def print_test(self):
        print("test")


class DummyDropbotServicePlugin(Plugin):
    id = 'dummy_dropbot_service.plugin'
    name = 'Dummy Dropbot Service Plugin'
    service_offers = List(contributes_to=SERVICE_OFFERS)

    # This tells us that the plugin contributes the value of this trait to the
    # 'actor topic routes' extension point.
    actor_topic_routing = List([{"example": ["a/b", "c/d"]}], contributes_to=ACTOR_TOPIC_ROUTES)

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_service),
        ]

    def _create_service(self, *args, **kwargs):
        """Create an analysis service."""
        return DropbotDummyMixinService

    @observe('application:started')
    def _on_application_started(self, event):
        self.application.get_plugin("dropbot_controller.plugin").dropbot_controller.print_test()
        publish_message(message="", topic=START_DEVICE_MONITORING)

    @observe('application:stopping')
    def _on_application_stopping(self, event):
        # create event loop
        while True:
            time.sleep(1)


def main(args):
    """Run the application."""

    # We will be adding a sample dummy dropbot service mixin plugin that will provide a module.submodule"

    plugins = [CorePlugin(), DropbotControllerPlugin(), DummyDropbotServicePlugin(), MessageRouterPlugin()]
    app = Application(plugins=plugins)

    # Need to run with a dramatiq broker context since app requires plugins that use dramatiq
    with redis_server_context(), dramatiq_workers_context():
        app.run()


if __name__ == "__main__":
    main(sys.argv)

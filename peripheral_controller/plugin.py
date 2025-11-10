from envisage.api import ServiceOffer
from envisage.ids import SERVICE_OFFERS
from envisage.plugin import Plugin
from traits.api import List

# local package imports
from .peripheral_controller_base import PeripheralControllerBase
from .interfaces.i_peripheral_control_mixin_service import IPeripheralControlMixinService
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name, DEVICE_NAME

# microdrop imports
from message_router.consts import ACTOR_TOPIC_ROUTES
from logger.logger_service import get_logger
# Initialize logger
logger = get_logger(__name__)


class PeripheralControllerPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # this plugin contributes some service offers
    service_offers = List(contributes_to=SERVICE_OFFERS)

    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(protocol=IPeripheralControlMixinService, factory=self._create_monitor_service),
            ServiceOffer(protocol=IPeripheralControlMixinService, factory=self._create_zstage_state_setter_service),
        ]

    def _create_monitor_service(self, *args, **kwargs):
        """Returns a dropbot monitor mixin service with core functionality."""
        from .services.peripheral_monitor_mixin_service import PeripheralMonitorMixinService
        return PeripheralMonitorMixinService

    def _create_zstage_state_setter_service(self, *args, **kwargs):
        """Returns a zstage mixin service to set z-stage states"""
        from .services.zstage_state_setter_service import ZStageStatesSetterMixinService
        return ZStageStatesSetterMixinService

    def start(self):
        """ Initialize the dropbot on plugin start """

        # Note that we always offer the service via its name, but look it up via the actual protocol.
        from .interfaces.i_peripheral_control_mixin_service import IPeripheralControlMixinService

        # Lookup the dropbot controller related mixin class services and add to base class.
        services = self.application.get_services(IPeripheralControlMixinService) + [PeripheralControllerBase]
        logger.debug(f"The following {DEVICE_NAME} services are going to be initialized: {services} ")

        # Create a new class that inherits from all services
        class Controller(*services):
            pass

        self.device_controller = Controller()

    def stop(self):
        """Cleanup when the plugin is stopped."""
        if hasattr(self, 'device_controller'):
            self.device_controller.cleanup()
            logger.info("DropbotController plugin stopped")

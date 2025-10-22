from envisage.api import ServiceOffer
from envisage.ids import SERVICE_OFFERS
from envisage.plugin import Plugin
from traits.api import List

from microdrop_application.helpers import get_microdrop_redis_globals_manager
# local package imports
from .dropbot_controller_base import DropbotControllerBase
from .interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name
from .services.dropbot_monitor_mixin_service import DropbotMonitorMixinService
from .services.dropbot_states_setting_mixin_service import DropbotStatesSettingMixinService
from .services.dropbot_self_tests_mixin_service import DropbotSelfTestsMixinService
from .services.droplet_detection_mixin_service import DropletDetectionMixinService
from .services.dropbot_settings_change import DropbotChangeSettingsService

# microdrop imports
from message_router.consts import ACTOR_TOPIC_ROUTES
from logger.logger_service import get_logger
# Initialize logger
logger = get_logger(__name__)


class DropbotControllerPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # this plugin contributes some service offers
    service_offers = List(contributes_to=SERVICE_OFFERS)

    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_monitor_service),
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_set_states_service),
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_self_test_service),
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_droplet_detection_service),
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_dropbot_change_settings_service),
        ]

    def _create_monitor_service(self, *args, **kwargs):
        """Returns a dropbot monitor mixin service with core functionality."""
        return DropbotMonitorMixinService

    def _create_set_states_service(self, *args, **kwargs):
        """Returns a dropbot set states mixin service with some basic states setting functionality."""
        return DropbotStatesSettingMixinService

    def _create_self_test_service(self, *args, **kwargs):
        """
        Returns a dropbot self test mixin service providing the ability to run all the dorpbot QC methods
        and generate a report.
        """
        return DropbotSelfTestsMixinService
    
    def _create_droplet_detection_service(self, *args, **kwargs):
        """Returns a droplet detection mixin service for detecting droplets on electrodes."""
        return DropletDetectionMixinService

    def _create_dropbot_change_settings_service(self, *args, **kwargs):
        """Returns a service to change settings for dropbot system"""
        return DropbotChangeSettingsService

    def start(self):
        """ Initialize the dropbot on plugin start """

        from .preferences import DropbotPreferences

        # Note that we always offer the service via its name, but look it up via the actual protocol.
        from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

        # Lookup the dropbot controller related mixin class services and add to base class.
        services = self.application.get_services(IDropbotControlMixinService) + [DropbotControllerBase]
        logger.debug(f"The following dropbot services are going to be initialized: {services} ")

        # Create a new class that inherits from all services
        class DropbotController(*services):
            pass

        self.dropbot_controller = DropbotController()
        self.dropbot_controller.preferences = DropbotPreferences(preferences=self.application.preferences)

        # push all preferences to globals
        app_globals = get_microdrop_redis_globals_manager()
        app_globals.update(self.dropbot_controller.preferences.preferences_name_map)

    def stop(self):
        """Cleanup when the plugin is stopped."""
        if hasattr(self, 'dropbot_controller'):
            self.dropbot_controller.cleanup()
            logger.info("DropbotController plugin stopped")

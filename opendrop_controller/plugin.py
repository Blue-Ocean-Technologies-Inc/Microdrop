from envisage.api import ServiceOffer
from envisage.ids import SERVICE_OFFERS
from envisage.plugin import Plugin
from traits.api import List

from logger.logger_service import get_logger
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.helpers import get_microdrop_redis_globals_manager

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name
from .interfaces.i_opendrop_control_mixin_service import IOpenDropControlMixinService
from .opendrop_controller_base import OpenDropControllerBase
from .preferences import OpenDropPreferences
from .services.opendrop_electrodes_mixin_service import OpenDropElectrodesMixinService
from .services.opendrop_monitor_mixin_service import OpenDropMonitorMixinService
from .services.opendrop_states_setting_mixin_service import OpenDropStatesSettingMixinService

logger = get_logger(__name__)


class OpenDropControllerPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    service_offers = List(contributes_to=SERVICE_OFFERS)
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def _service_offers_default(self):
        return [
            ServiceOffer(
                protocol=IOpenDropControlMixinService,
                factory=self._create_monitor_service,
            ),
            ServiceOffer(
                protocol=IOpenDropControlMixinService,
                factory=self._create_states_service,
            ),
            ServiceOffer(
                protocol=IOpenDropControlMixinService,
                factory=self._create_electrodes_service,
            ),
        ]

    @staticmethod
    def _create_monitor_service(*args, **kwargs):
        return OpenDropMonitorMixinService

    @staticmethod
    def _create_states_service(*args, **kwargs):
        return OpenDropStatesSettingMixinService

    @staticmethod
    def _create_electrodes_service(*args, **kwargs):
        return OpenDropElectrodesMixinService

    def start(self):
        services = self.application.get_services(IOpenDropControlMixinService) + [OpenDropControllerBase]
        logger.info(f"Initializing OpenDrop services: {services}")

        class OpenDropController(*services):
            pass

        self.opendrop_controller = OpenDropController()
        self.opendrop_controller.preferences = OpenDropPreferences(preferences=self.application.preferences)
        self.opendrop_controller.feedback_enabled = bool(self.opendrop_controller.preferences.feedback_enabled)
        self.opendrop_controller.set_temperatures = [
            int(self.opendrop_controller.preferences.temperature_1),
            int(self.opendrop_controller.preferences.temperature_2),
            int(self.opendrop_controller.preferences.temperature_3),
        ]

        app_globals = get_microdrop_redis_globals_manager()
        app_globals.update(self.opendrop_controller.preferences.preferences_name_map)

    def stop(self):
        if hasattr(self, "opendrop_controller"):
            self.opendrop_controller.cleanup()
            logger.info("OpenDropController plugin stopped")

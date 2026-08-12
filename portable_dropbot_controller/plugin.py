from envisage.api import ServiceOffer
from envisage.ids import SERVICE_OFFERS
from envisage.plugin import Plugin
from traits.api import List

from logger.logger_service import get_logger
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.helpers import get_microdrop_redis_globals_manager

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name
from .interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from .portable_dropbot_controller_base import PortableDropbotControllerBase
from .preferences import PortableDropbotPreferences
from .services.portable_dropbot_electrodes_mixin_service import (
    PortableDropbotElectrodesMixinService,
)
from .services.portable_dropbot_monitor_mixin_service import (
    PortableDropbotMonitorMixinService,
)
from .services.portable_dropbot_motors_mixin_service import (
    PortableDropbotMotorsMixinService,
)
from .services.portable_dropbot_states_setting_mixin_service import (
    PortableDropbotStatesSettingMixinService,
)

logger = get_logger(__name__)


class PortableDropbotControllerPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    service_offers = List(contributes_to=SERVICE_OFFERS)
    actor_topic_routing = List([ACTOR_TOPIC_DICT],
                               contributes_to=ACTOR_TOPIC_ROUTES)

    def _service_offers_default(self):
        return [
            ServiceOffer(protocol=IPortableDropbotControlMixinService,
                         factory=self._create_monitor_service),
            ServiceOffer(protocol=IPortableDropbotControlMixinService,
                         factory=self._create_states_service),
            ServiceOffer(protocol=IPortableDropbotControlMixinService,
                         factory=self._create_electrodes_service),
            ServiceOffer(protocol=IPortableDropbotControlMixinService,
                         factory=self._create_motors_service),
        ]

    @staticmethod
    def _create_monitor_service(*args, **kwargs):
        return PortableDropbotMonitorMixinService

    @staticmethod
    def _create_states_service(*args, **kwargs):
        return PortableDropbotStatesSettingMixinService

    @staticmethod
    def _create_electrodes_service(*args, **kwargs):
        return PortableDropbotElectrodesMixinService

    @staticmethod
    def _create_motors_service(*args, **kwargs):
        return PortableDropbotMotorsMixinService

    def start(self):
        services = self.application.get_services(
            IPortableDropbotControlMixinService) \
            + [PortableDropbotControllerBase]
        logger.info(f"Initializing Portable Dropbot services: "
                    f"{services}")

        class PortableDropbotController(*services):
            pass

        self.portable_dropbot_controller = PortableDropbotController()
        self.portable_dropbot_controller.preferences = \
            PortableDropbotPreferences(
                preferences=self.application.preferences)

        app_globals = get_microdrop_redis_globals_manager()
        app_globals.update(
            self.portable_dropbot_controller.preferences
            .preferences_name_map)

        self.portable_dropbot_controller \
            .on_start_device_monitoring_request()

    def stop(self):
        if hasattr(self, "portable_dropbot_controller"):
            self.portable_dropbot_controller.cleanup()
            logger.info("PortableDropbotController plugin stopped")

from envisage.api import ServiceOffer
from traits.api import List

# local package imports
from .peripheral_controller_base import PeripheralControllerBase
from .interfaces.i_peripheral_control_mixin_service import IPeripheralControlMixinService
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name

# microdrop imports
from message_router.consts import ACTOR_TOPIC_ROUTES
from peripheral_device_controller_base.plugin import PeripheralDeviceControllerPlugin
from logger.logger_service import get_logger
# Initialize logger
logger = get_logger(__name__)


class PeripheralControllerPlugin(PeripheralDeviceControllerPlugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    # Compose only the magnet's own mixins onto the magnet's controller base.
    _mixin_protocol = IPeripheralControlMixinService
    _controller_base_class = PeripheralControllerBase

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(protocol=IPeripheralControlMixinService, factory=self._create_monitor_service),
            ServiceOffer(protocol=IPeripheralControlMixinService, factory=self._create_zstage_state_setter_service),
        ]

    def _create_monitor_service(self, *args, **kwargs):
        """Returns a peripheral monitor mixin service with core functionality."""
        from .services.peripheral_monitor_mixin_service import PeripheralMonitorMixinService
        return PeripheralMonitorMixinService

    def _create_zstage_state_setter_service(self, *args, **kwargs):
        """Returns a zstage mixin service to set z-stage states"""
        from .services.zstage_state_setter_service import ZStageStatesSetterMixinService
        return ZStageStatesSetterMixinService

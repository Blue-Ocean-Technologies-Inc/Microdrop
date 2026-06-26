from envisage.api import ServiceOffer
from traits.api import List

from message_router.consts import ACTOR_TOPIC_ROUTES
from peripheral_device_controller_base.plugin import PeripheralDeviceControllerPlugin
from logger.logger_service import get_logger

from .heater_controller_base import HeaterControllerBase
from .interfaces.i_heater_control_mixin_service import IHeaterControlMixinService
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name

logger = get_logger(__name__)


class HeaterControllerPlugin(PeripheralDeviceControllerPlugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # This plugin contributes actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    # Compose only the heater's own mixins onto the heater's controller base.
    _mixin_protocol = IHeaterControlMixinService
    _controller_base_class = HeaterControllerBase

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(protocol=IHeaterControlMixinService, factory=self._create_monitor_service),
            ServiceOffer(protocol=IHeaterControlMixinService, factory=self._create_command_setter_service),
        ]

    def _create_monitor_service(self, *args, **kwargs):
        """Returns the heater monitor mixin service."""
        from .services.heater_monitor_mixin_service import HeaterMonitorMixinService
        return HeaterMonitorMixinService

    def _create_command_setter_service(self, *args, **kwargs):
        """Returns the heater command-setter mixin service."""
        from .services.heater_command_setter_service import HeaterCommandSetterService
        return HeaterCommandSetterService

from envisage.api import ServiceOffer
from envisage.ids import SERVICE_OFFERS
from envisage.plugin import Plugin
from traits.api import List

from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
# local package imports
from .consts import PKG, PKG_name

from .services.electrode_state_change_service import ElectrodeStateChangeMixinService
from .services.electrode_disable_service import ElectrodeDisableMixinService

# Initialize logger
from logger.logger_service import get_logger
logger = get_logger(__name__)


class ElectrodeControllerPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # this plugin contributes some service offers
    service_offers = List(contributes_to=SERVICE_OFFERS)

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_electrode_state_change_service),
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_electrode_disable_service),
        ]

    def _create_electrode_state_change_service(self, *args, **kwargs):
        """Create the electrode state change mixin service."""
        return ElectrodeStateChangeMixinService

    def _create_electrode_disable_service(self, *args, **kwargs):
        """Create the electrode disable mixin service."""
        return ElectrodeDisableMixinService

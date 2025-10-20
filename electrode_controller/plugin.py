from envisage.api import ServiceOffer
from envisage.ids import SERVICE_OFFERS
from envisage.plugin import Plugin
from traits.api import List

from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
# local package imports
from .consts import PKG, PKG_name

# microdrop imports
from microdrop_utils._logger import get_logger
from .services.electrode_state_change_service import ElectrodeStateChangeMixinService

# Initialize logger
logger = get_logger(__name__)


class ElectrodeControllerPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # this plugin contributes some service offers
    service_offers = List(contributes_to=SERVICE_OFFERS)

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(protocol=IDropbotControlMixinService, factory=self._create_service),
        ]

    def _create_service(self, *args, **kwargs):
        """Create an analysis service."""
        return ElectrodeStateChangeMixinService

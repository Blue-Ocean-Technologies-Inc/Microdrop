from envisage.ids import SERVICE_OFFERS
from envisage.plugin import Plugin
from traits.api import List

from message_router.consts import ACTOR_TOPIC_ROUTES
from logger.logger_service import get_logger

from .peripheral_device_controller_base import PeripheralDeviceControllerBase
from .interfaces.i_peripheral_device_control_mixin_service import IPeripheralDeviceControlMixinService

logger = get_logger(__name__)


class PeripheralDeviceControllerPlugin(Plugin):
    """Generic backend plugin that composes a device's controller base with all
    of its mixin services into a single ``Controller`` instance.

    Subclasses MUST set:
        ``id`` / ``name``        — Envisage plugin identity.
        ``actor_topic_routing``  — ``List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)``.
        ``_mixin_protocol``      — the device's OWN ``IPeripheralDeviceControlMixinService``
                                   subclass (so only that device's mixins are composed).
        ``_controller_base_class`` — the device's ``PeripheralDeviceControllerBase`` subclass.
    And override ``_service_offers_default`` to register the device's mixin services.
    """

    # this plugin contributes some service offers
    service_offers = List(contributes_to=SERVICE_OFFERS)

    # device-specific composition knobs (overridden by subclasses)
    _mixin_protocol = IPeripheralDeviceControlMixinService
    _controller_base_class = PeripheralDeviceControllerBase

    def _service_offers_default(self):
        """Subclasses return the ServiceOffers for their mixin services."""
        return []

    def start(self):
        """Compose the controller base + all mixin services and instantiate it."""
        # Look up the device's mixin services (registered under its own protocol)
        services = self.application.get_services(self._mixin_protocol) + [self._controller_base_class]
        logger.debug(f"The following services are going to be initialized: {services} ")

        # Create a new class that inherits from all services
        class Controller(*services):
            pass

        self.device_controller = Controller()

    def stop(self):
        """Cleanup when the plugin is stopped."""
        if hasattr(self, 'device_controller'):
            self.device_controller.cleanup()
            logger.info(f"{self.device_controller._device_name.title()} Controller plugin stopped")

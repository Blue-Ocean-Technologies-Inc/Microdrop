# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from envisage.api import ServiceOffer
from envisage.ids import SERVICE_OFFERS
from envisage.plugin import Plugin
from traits.api import List

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Local imports.
from .consts import (
    ACTOR_TOPIC_DICT,
    DEFAULT_PROTOCOL_FREQUENCY_RANGE,
    DEFAULT_PROTOCOL_VOLTAGE_RANGE,
    PKG,
    PROTOCOL_FREQUENCY_RANGE_KEY,
    PROTOCOL_VOLTAGE_RANGE_KEY,
    PKG_name,
)
from .dropbot_controller_base import DropbotControllerBase
from .interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from .services.dropbot_monitor_mixin_service import DropbotMonitorMixinService
from .services.dropbot_self_tests_mixin_service import DropbotSelfTestsMixinService
from .services.dropbot_settings_change import DropbotChangeSettingsService
from .services.dropbot_states_setting_mixin_service import (
    DropbotStatesSettingMixinService,
)
from .services.droplet_detection_mixin_service import DropletDetectionMixinService

# Logger import.
from logger.logger_service import get_logger

# Initialize logger
logger = get_logger(__name__)


class DropbotControllerPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    # this plugin contributes some service offers
    service_offers = List(contributes_to=SERVICE_OFFERS)

    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def _service_offers_default(self):
        """Return the service offers."""
        return [
            ServiceOffer(
                protocol=IDropbotControlMixinService,
                factory=self._create_monitor_service,
            ),
            ServiceOffer(
                protocol=IDropbotControlMixinService,
                factory=self._create_set_states_service,
            ),
            ServiceOffer(
                protocol=IDropbotControlMixinService,
                factory=self._create_self_test_service,
            ),
            ServiceOffer(
                protocol=IDropbotControlMixinService,
                factory=self._create_droplet_detection_service,
            ),
            ServiceOffer(
                protocol=IDropbotControlMixinService,
                factory=self._create_dropbot_change_settings_service,
            ),
        ]

    def _create_monitor_service(self, *args, **kwargs):
        """Returns a dropbot monitor mixin service with core functionality."""
        return DropbotMonitorMixinService

    def _create_set_states_service(self, *args, **kwargs):
        """Returns a dropbot set states mixin service with basic state setting."""
        return DropbotStatesSettingMixinService

    def _create_self_test_service(self, *args, **kwargs):
        """
        Returns a dropbot self test mixin service providing the ability to run all
        the dropbot QC methods and generate a report.
        """
        return DropbotSelfTestsMixinService

    def _create_droplet_detection_service(self, *args, **kwargs):
        """Returns a droplet detection mixin service for detecting droplets."""
        return DropletDetectionMixinService

    def _create_dropbot_change_settings_service(self, *args, **kwargs):
        """Returns a service to change settings for dropbot system"""
        return DropbotChangeSettingsService

    def start(self):
        """Initialize the dropbot on plugin start"""

        # Note that we always offer the service via its name, but look it up via
        # the actual protocol.
        from dropbot_controller.interfaces.i_dropbot_control_mixin_service import (
            IDropbotControlMixinService,
        )

        from .preferences import DropbotPreferences

        # Lookup the dropbot controller related mixin class services and add to
        # base class.
        services = self.application.get_services(IDropbotControlMixinService) + [
            DropbotControllerBase
        ]
        logger.debug(
            f"The following dropbot services are going to be initialized: {services} "
        )

        # Create a new class that inherits from all services
        class DropbotController(*services):
            pass

        self.dropbot_controller = DropbotController()
        self.dropbot_controller.preferences = DropbotPreferences(
            preferences=self.application.preferences
        )

        # push all preferences to globals
        app_globals = get_microdrop_redis_globals_manager()
        app_globals.update(self.dropbot_controller.preferences.preferences_name_map)

        # Overwrite, never seed: app_globals outlives the session, so a
        # previous device's range would otherwise bound the protocol columns.
        # DropbotPreferences refines the maxima once the DropBot reports its
        # own on connect.
        app_globals[PROTOCOL_VOLTAGE_RANGE_KEY] = DEFAULT_PROTOCOL_VOLTAGE_RANGE
        app_globals[PROTOCOL_FREQUENCY_RANGE_KEY] = DEFAULT_PROTOCOL_FREQUENCY_RANGE

    def stop(self):
        """Cleanup when the plugin is stopped."""
        if hasattr(self, "dropbot_controller"):
            self.dropbot_controller.cleanup()
            logger.info("DropbotController plugin stopped")

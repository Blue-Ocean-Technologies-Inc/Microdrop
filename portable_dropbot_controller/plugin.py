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
    FREQUENCY_BOUNDS,
    PKG,
    PROTOCOL_FREQUENCY_RANGE_KEY,
    PROTOCOL_VOLTAGE_RANGE_KEY,
    VOLTAGE_BOUNDS,
    PKG_name,
)
from .interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from .portable_dropbot_controller_base import PortableDropbotControllerBase
from .preferences import PortableDropbotPreferences
from .services.portable_dropbot_calibration_mixin_service import (
    PortableDropbotCalibrationMixinService,
)
from .services.portable_dropbot_droplet_detection_mixin_service import (
    PortableDropbotDropletDetectionMixinService,
)
from .services.portable_dropbot_electrodes_mixin_service import (
    PortableDropbotElectrodesMixinService,
)
from .services.portable_dropbot_fluorescence_mixin_service import (
    FluorescenceCaptureMixinService,
)
from .services.portable_dropbot_heater_tune_mixin_service import (
    PortableDropbotHeaterTuneMixinService,
)
from .services.portable_dropbot_heater_tune_verify_mixin_service import (
    PortableDropbotHeaterTuneVerifyMixinService,
)
from .services.portable_dropbot_monitor_mixin_service import (
    PortableDropbotMonitorMixinService,
)
from .services.portable_dropbot_motors_mixin_service import (
    PortableDropbotMotorsMixinService,
)
from .services.portable_dropbot_pmt_mixin_service import (
    PortableDropbotPmtMixinService,
)
from .services.portable_dropbot_self_test_mixin_service import (
    PortableDropbotSelfTestMixinService,
)
from .services.portable_dropbot_self_test_state_mixin_service import (
    PortableDropbotSelfTestStateMixinService,
)
from .services.portable_dropbot_states_setting_mixin_service import (
    PortableDropbotStatesSettingMixinService,
)
from .services.portable_dropbot_system_mixin_service import (
    PortableDropbotSystemMixinService,
)
from .services.portable_dropbot_temp_mixin_service import (
    PortableDropbotTempMixinService,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PortableDropbotControllerPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    service_offers = List(contributes_to=SERVICE_OFFERS)
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def _service_offers_default(self):
        return [
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_monitor_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_states_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_electrodes_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_motors_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_calibration_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_droplet_detection_service,
            ),
            # Before the temp and self-test mixins: its _exclusive_owner_reason,
            # _on_request_refused and on_alarm_signal must run first and
            # chain to theirs (the composed class's MRO follows this order).
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_heater_tune_service,
            ),
            # Its runs share the heater-tune mixin's claim; same placement
            # (its _on_request_refused must chain before the self-test's).
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_heater_tune_verify_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_temp_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_pmt_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_fluorescence_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_system_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_self_test_service,
            ),
            ServiceOffer(
                protocol=IPortableDropbotControlMixinService,
                factory=self._create_self_test_state_service,
            ),
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

    @staticmethod
    def _create_calibration_service(*args, **kwargs):
        return PortableDropbotCalibrationMixinService

    @staticmethod
    def _create_droplet_detection_service(*args, **kwargs):
        return PortableDropbotDropletDetectionMixinService

    @staticmethod
    def _create_heater_tune_service(*args, **kwargs):
        return PortableDropbotHeaterTuneMixinService

    @staticmethod
    def _create_heater_tune_verify_service(*args, **kwargs):
        return PortableDropbotHeaterTuneVerifyMixinService

    @staticmethod
    def _create_temp_service(*args, **kwargs):
        return PortableDropbotTempMixinService

    @staticmethod
    def _create_pmt_service(*args, **kwargs):
        return PortableDropbotPmtMixinService

    @staticmethod
    def _create_fluorescence_service(*args, **kwargs):
        return FluorescenceCaptureMixinService

    @staticmethod
    def _create_system_service(*args, **kwargs):
        return PortableDropbotSystemMixinService

    @staticmethod
    def _create_self_test_service(*args, **kwargs):
        return PortableDropbotSelfTestMixinService

    @staticmethod
    def _create_self_test_state_service(*args, **kwargs):
        return PortableDropbotSelfTestStateMixinService

    def start(self):
        services = self.application.get_services(
            IPortableDropbotControlMixinService
        ) + [PortableDropbotControllerBase]
        logger.info(f"Initializing Portable Dropbot services: {services}")

        class PortableDropbotController(*services):
            pass

        self.portable_dropbot_controller = PortableDropbotController()

        # Rewrite the realtime-mode key an earlier session left in Redis.
        self.portable_dropbot_controller.realtime_mode = False

        self.portable_dropbot_controller.preferences = PortableDropbotPreferences(
            preferences=self.application.preferences
        )

        app_globals = get_microdrop_redis_globals_manager()
        app_globals.update(
            self.portable_dropbot_controller.preferences.preferences_name_map
        )

        # Overwrite, never seed: app_globals outlives the session, so a
        # previous device's range would otherwise bound the protocol columns.
        app_globals[PROTOCOL_VOLTAGE_RANGE_KEY] = list(VOLTAGE_BOUNDS)
        app_globals[PROTOCOL_FREQUENCY_RANGE_KEY] = list(FREQUENCY_BOUNDS)

        self.portable_dropbot_controller.on_start_device_monitoring_request()

    def stop(self):
        if hasattr(self, "portable_dropbot_controller"):
            self.portable_dropbot_controller.cleanup()
            logger.info("PortableDropbotController plugin stopped")

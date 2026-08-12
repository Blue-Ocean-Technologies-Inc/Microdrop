from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger

from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

logger = get_logger(__name__)


@provides(IPortableDropbotControlMixinService)
class PortableDropbotStatesSettingMixinService(HasTraits):
    id = Str("portable_dropbot_states_setting_mixin_service")
    name = Str("Portable Dropbot States Setting Mixin")

    def on_set_realtime_mode_request(self, message):
        self.realtime_mode = str(message) == "True"
        self._publish_realtime_mode()
        if not self.realtime_mode:
            # Leaving realtime mode releases every electrode, exactly
            # as the other backends do.
            self._proxy_call("clear channels",
                             lambda: self.proxy.clear_channels())
        logger.info(f"Portable Dropbot realtime mode set to "
                    f"{self.realtime_mode}")

    def on_set_voltage_request(self, message):
        self.voltage = int(float(str(message)))
        self._apply_actuation()
        logger.info(f"Portable Dropbot voltage set to {self.voltage} V")

    def on_set_frequency_request(self, message):
        self.frequency = int(float(str(message)))
        self._apply_actuation()
        logger.info(f"Portable Dropbot frequency set to "
                    f"{self.frequency} Hz")

    def on_set_light_intensity_request(self, message):
        self.light_intensity = int(float(str(message)))
        self._apply_light_intensity()
        if self.preferences is not None:
            # Persisted as the next connect's default, as before.
            self.preferences.default_light_intensity = \
                self.light_intensity
        logger.info(f"Portable Dropbot light intensity set to "
                    f"{self.light_intensity} %")

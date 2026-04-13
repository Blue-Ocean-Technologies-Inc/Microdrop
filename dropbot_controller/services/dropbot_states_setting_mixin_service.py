from traits.api import provides, HasTraits, Bool, Float, Str

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

from ..consts import REALTIME_MODE_UPDATED, HARDWARE_MIN_VOLTAGE, HARDWARE_MIN_FREQUENCY


logger = get_logger(__name__)


@provides(IDropbotControlMixinService)
class DropbotStatesSettingMixinService(HasTraits):
    """
    A mixin Class that adds methods to set states for a dropbot connection and get some dropbot information.
    """

    id = Str('dropbot_states_setting_mixin_service')
    name = Str('Dropbot States Setting Mixin')

    realtime_mode = Bool(False)
    # TODO: Get these from a config file
    voltage = Float(30)
    frequency = Float(1000)

    ######################################## Methods to Expose #############################################

    @property
    def hardware_max_voltage(self):
        """Maximum voltage supported by the connected DropBot hardware."""
        try:
            with self.proxy.transaction_lock:
                max_voltage = self.proxy.config.max_voltage
        except Exception as e:
            logger.error(e, exc_info=True)
            max_voltage = 140

        return max_voltage

    @property
    def hardware_max_frequency(self):
        """Maximum frequency supported by the connected DropBot hardware."""
        try:
            with self.proxy.transaction_lock:
                max_freq = self.proxy.config.max_frequency
        except Exception as e:
            logger.error(e, exc_info=True)
            max_freq = 10_000

        return max_freq

    def on_set_voltage_request(self, message):
        """Set voltage on the dropbot device.

        Validates against known hardware minimum (from consts) and the
        connected device's max_voltage (from proxy.config).
        """
        try:
            self.voltage = float(message)
            if self.voltage < HARDWARE_MIN_VOLTAGE or self.voltage > self.hardware_max_voltage:
                raise ValueError(
                    f"Voltage must be between {HARDWARE_MIN_VOLTAGE} and {self.hardware_max_voltage} V"
                )

            self.preferences.last_voltage = int(self.voltage)

            if not hasattr(self, 'proxy') or self.proxy is None:
                logger.error("Proxy not available for voltage setting")
                return

            if self.realtime_mode:
                with self.proxy.transaction_lock:
                        self.proxy.update_state(voltage=self.voltage)
                        logger.info(f"Set voltage to {self.voltage} V")

        except (TimeoutError, RuntimeError) as e:
            logger.error(f"Proxy error setting voltage: {e}")
        except Exception as e:
            logger.error(f"Error setting voltage: {e}")
            raise

    def on_set_frequency_request(self, message):
        """Set frequency on the dropbot device.

        Validates against known hardware minimum (from consts) and the
        connected device's max_frequency (from proxy.config).
        """
        try:
            self.frequency = float(message)
            if self.frequency < HARDWARE_MIN_FREQUENCY or self.frequency > self.hardware_max_frequency:
                raise ValueError(
                    f"Frequency must be between {HARDWARE_MIN_FREQUENCY} and {self.hardware_max_frequency} Hz"
                )

            self.preferences.last_frequency = int(self.frequency)

            if not hasattr(self, 'proxy') or self.proxy is None:
                logger.error("Proxy not available for frequency setting")
                return

            if self.realtime_mode:
                with self.proxy.transaction_lock:
                        self.proxy.update_state(frequency=self.frequency)
                        logger.info(f"Set frequency to {self.frequency} Hz")

        except (TimeoutError, RuntimeError) as e:
            logger.error(f"Proxy error setting frequency: {e}")
        except Exception as e:
            logger.error(f"Error setting frequency: {e}")
            raise

    def on_set_realtime_mode_request(self, message):
        """
        Method to set the realtime mode on the dropbot device.
        """
        try:
            if not hasattr(self, 'proxy') or self.proxy is None:
                logger.error("Proxy not available for realtime mode setting")
                return

            with self.proxy.transaction_lock:
                if message == "True":
                    self.realtime_mode = True
                    self.proxy.update_state(hv_output_selected=True,
                                            hv_output_enabled=True,
                                            )
                    publish_message(topic=REALTIME_MODE_UPDATED, message="True")
                else:
                    self.realtime_mode = False
                    self.proxy.update_state(hv_output_enabled=False)
                    publish_message(topic=REALTIME_MODE_UPDATED, message="False")
                logger.info(f"Set realtime mode to {self.realtime_mode}")

        except (TimeoutError, RuntimeError) as e:
            logger.error(f"Proxy error setting realtime mode: {e}")
        except Exception as e:
            logger.error(f"Error setting realtime mode: {e}")

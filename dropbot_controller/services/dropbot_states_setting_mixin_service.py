from traits.api import provides, HasTraits, Bool, Float, Str

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

from ..consts import REALTIME_MODE_UPDATED


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

    def on_set_voltage_request(self, message):
        """
        Method to set the voltage on the dropbot device.
        """
        try:
            self.voltage = float(message)
            if self.voltage < 30 or self.voltage > 150:
                raise ValueError("Voltage must be between 30 and 150 V")

            self.preferences.default_voltage = int(self.voltage)

            if not hasattr(self, 'proxy') or self.proxy is None:
                logger.error("Proxy not available for voltage setting")
                return

            with self.proxy.transaction_lock:
                if self.realtime_mode:
                    self.proxy.update_state(voltage=self.voltage)
                else:
                    self.proxy.update_state(
                        hv_output_enabled=False,
                        voltage=self.voltage)
                logger.info(f"Set voltage to {self.voltage} V")

        except (TimeoutError, RuntimeError) as e:
            logger.error(f"Proxy error setting voltage: {e}")
        except Exception as e:
            logger.error(f"Error setting voltage: {e}")
            raise

    def on_set_frequency_request(self, message):
        """
        Method to set the frequency on the dropbot device.
        """
        try:
            self.frequency = float(message)
            if self.frequency < 100 or self.frequency > 20000:
                raise ValueError("Frequency must be between 100 and 20000 Hz")

            self.preferences.default_frequency= int(self.frequency)

            if not hasattr(self, 'proxy') or self.proxy is None:
                logger.error("Proxy not available for frequency setting")
                return

            with self.proxy.transaction_lock:
                if self.realtime_mode:
                    self.proxy.update_state(frequency=self.frequency)
                else:
                    self.proxy.update_state(
                        hv_output_enabled=False,
                        frequency=self.frequency)
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
                                            # voltage=self.voltage,
                                            # frequency=self.frequency
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

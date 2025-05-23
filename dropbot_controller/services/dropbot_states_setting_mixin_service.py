from traits.api import provides, HasTraits, Bool, Float

from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.decorators import debounce

from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

from ..consts import REALTIME_MODE_UPDATED


logger = get_logger(__name__, level="DEBUG")


@provides(IDropbotControlMixinService)
class DropbotStatesSettingMixinService(HasTraits):
    """
    A mixin Class that adds methods to set states for a dropbot connection and get some dropbot information.
    """

    id = "dropbot_states_setting_mixin_service"
    name = 'Dropbot States Setting Mixin'
    realtime_mode = Bool(False)
    # TODO: Get these from a config file
    voltage = Float(30)
    frequency = Float(1000)

    ######################################## Methods to Expose #############################################
    @debounce(wait_seconds=0.5)
    def on_set_voltage_request(self, message):
        """
        Method to set the voltage on the dropbot device.
        """
        try:
            self.voltage = float(message)
            if self.realtime_mode:
                self.proxy.update_state(voltage=self.voltage)
            else:
                self.proxy.update_state(
                    hv_output_enabled=False,
                    voltage=self.voltage)
            logger.info(f"Set voltage to {self.voltage} V")
        except Exception as e:
            logger.error(f"Error setting voltage: {e}")
            raise

    @debounce(wait_seconds=0.5)
    def on_set_frequency_request(self, message):
        """
        Method to set the frequency on the dropbot device.
        """
        try:
            self.frequency = float(message)
            if self.realtime_mode:
                self.proxy.update_state(frequency=self.frequency)
            else:
                self.proxy.update_state(
                    hv_output_enabled=False,
                    frequency=self.frequency)
            logger.info(f"Set frequency to {self.frequency} Hz")
        except Exception as e:
            logger.error(f"Error setting frequency: {e}")
            raise

    @debounce(wait_seconds=1.0)
    def on_set_realtime_mode_request(self, message):
        """
        Method to set the realtime mode on the dropbot device.
        """
        # update_state doesn't return anything useful, and theres no way to register callbacks using signals.signal.connect, so we just assume that
        # if it doesn't return an error, then it worked.
        # TODO: Once acks are working firmware side, we can use that to confirm that the message was received.
        if message == "True":
            self.realtime_mode = True
            self.proxy.update_state(hv_output_selected=True,
                                    hv_output_enabled=True,
                                    voltage=self.voltage,
                                    frequency=self.frequency)
            publish_message(topic=REALTIME_MODE_UPDATED, message="True")
        else:
            self.realtime_mode = False
            self.proxy.update_state(hv_output_enabled=False)
            publish_message(topic=REALTIME_MODE_UPDATED, message="False")
        logger.info(f"Set realtime mode to {self.realtime_mode}")

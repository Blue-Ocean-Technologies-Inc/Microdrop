import json
from datetime import datetime

from dropbot import EVENT_CHANNELS_UPDATED, EVENT_SHORTS_DETECTED, EVENT_ENABLE, EVENT_DROPS_DETECTED, EVENT_ACTUATED_CHANNEL_CAPACITANCES
from traits.api import Instance, Dict
import dramatiq
from dramatiq.middleware import CurrentMessage

# unit handling
from pint import UnitRegistry

from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor, invoke_class_method, TimestampedMessage

ureg = UnitRegistry()

from .consts import (CHIP_INSERTED, CAPACITANCE_UPDATED, HALTED, HALT, START_DEVICE_MONITORING,
                     RETRY_CONNECTION, OUTPUT_ENABLE_PIN, SHORTS_DETECTED, PKG, DROPBOT_SETUP_SUCCESS)

from .interfaces.i_dropbot_controller_base import IDropbotControllerBase

from traits.api import HasTraits, provides, Bool
from microdrop_utils.dramatiq_dropbot_serial_proxy import DramatiqDropbotSerialProxy, CONNECTED, DISCONNECTED
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from microdrop_utils._logger import get_logger

logger = get_logger(__name__, level="DEBUG")


@provides(IDropbotControllerBase)
class DropbotControllerBase(HasTraits):
    """
    This class provides some methods for handling signals from the proxy. But mainly provides a dramatiq listener
    that captures appropriate signals and calls the methods needed.
    """
    proxy = Instance(DramatiqDropbotSerialProxy)
    dropbot_connection_active = Bool(False)

    ##########################################################
    # 'IDramatiqControllerBase' interface.
    ##########################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    listener_name = f"{PKG}_listener"
    
    timestamps = Dict(str, datetime)

    def __del__(self):
        """Cleanup when the controller is destroyed."""
        self.cleanup()

    def cleanup(self):
        """Cleanup resources when the controller is stopped."""
        logger.info("Cleaning up DropbotController resources")
        if self.proxy is not None:
            try:
                self.proxy.terminate()
                logger.info("Dropbot proxy terminated")
            except Exception as e:
                logger.error(f"Error terminating dropbot proxy: {e}")
            finally:
                self.proxy = None
                self.dropbot_connection_active = False

    def listener_actor_routine(self, timestamped_message: TimestampedMessage, topic: str):
        """
        A Dramatiq actor that listens to messages.

        Parameters:
        message (str): The received message.
        topic (str): The topic of the message.

        """
      
        logger.debug(f"DROPBOT BACKEND LISTENER: Received message: '{timestamped_message}' from topic: {topic} at {timestamped_message.timestamp}")

        # find the topics hierarchy: first element is the head topic. Last element is the specific topic
        topics_tree = topic.split("/")
        head_topic = topics_tree[0]
        primary_sub_topic = topics_tree[1]
        specific_sub_topic = topics_tree[-1]

        # set requested method to None for now
        requested_method = None

        # Determine the requested method to call based on the topic, if it is a dropbot request or signal topic
        # for external dropbot signals connected/disconnected, we handle them everytime. For requests,
        # we need to check if we have a dropbot available or not. Unless it is a request to start looking for a
        # device or disconnect the device.

        # 1. Check if it is a dropbot related topic
        if head_topic == 'dropbot':

            # 2. Handle the connected / disconnected signals
            if topic in [CONNECTED, DISCONNECTED]:
                requested_method = f"on_{specific_sub_topic}_signal"
            # Handle setup success signal
            elif topic == DROPBOT_SETUP_SUCCESS:
                self.dropbot_connection_active = True
                logger.info("Dropbot connection activated")
                return

            # 3. Handle specific dropbot requests that would change dropbot connectivity
            ## 3.1. Request to activate dropbot connection
            elif topic in [START_DEVICE_MONITORING, RETRY_CONNECTION]:
                if not self.dropbot_connection_active:
                    requested_method = f"on_{specific_sub_topic}_request"
                    logger.debug(f"Executing {specific_sub_topic} method as Dropbot is currently disconnected.")

            # 4. Handle all other requests
            elif primary_sub_topic == 'requests':
                if self.dropbot_connection_active:
                    requested_method = f"on_{specific_sub_topic}_request"
                else:
                    logger.warning(f"Request for {specific_sub_topic} denied: Dropbot is disconnected.")

        else:
            logger.debug(f"Ignored request from topic '{topic}': Not a Dropbot-related request.")

        if requested_method:
            if self.timestamps.get(topic, datetime.min) > timestamped_message.timestamp_dt:
                logger.debug(f"DropbotController: Ignoring older message from topic: {topic} received at {timestamped_message.timestamp_dt}")
                return
            self.timestamps[topic] = timestamped_message.timestamp_dt
            
            err_msg = invoke_class_method(self, requested_method, timestamped_message)

            if err_msg:
                logger.error(
                    f" {self.listener_name}; Received message: {timestamped_message} from topic: {topic} Failed to execute due to "
                    f"error: {err_msg}")

    def traits_init(self):
        """
        This function needs to be here to let the listener be initialized to the default value automatically.
        We just do it manually here to make the code clearer.
        We can also do other initialization routines here if needed.

        This is equivalent to doing:

        def __init__(self, **traits):
            super().__init__(**traits)

        """

        logger.info("Starting DropbotController listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine)

    ######################################################################
    # Proxy signal handlers
    #######################################################################

    # proxy signal handlers done this way so that these methods can be overrided externally

    def _on_dropbot_proxy_connected(self):
        
        # Initialize switching boards
        self.proxy.initialize_switching_boards()
        
        # Initial Proxy State Update
        # TODO: capacitance update interval should be set by the UI [default 100ms]
        self.proxy.update_state(capacitance_update_interval_ms=100,
                                hv_output_selected=False,
                                hv_output_enabled=False,
                                event_mask=EVENT_CHANNELS_UPDATED |
                                            EVENT_SHORTS_DETECTED |
                                            EVENT_ENABLE)
        
        # Connect proxy signals
        logger.debug(f"Connecting DropBot BLINKER signals to handlers")
        self.proxy.signals.signal('halted').connect(self._halted_event_wrapper, weak=False)
        self.proxy.signals.signal('output_enabled').connect(self._output_state_changed_wrapper, weak=False)
        self.proxy.signals.signal('output_disabled').connect(self._output_state_changed_wrapper, weak=False)
        self.proxy.signals.signal('capacitance-updated').connect(self._capacitance_updated_wrapper)
        self.proxy.signals.signal('shorts-detected').connect(self._shorts_detected_wrapper)
        
        # If the feedback capacitor is < 300nF, disable the chip load
        # saturation check to prevent false positive triggers.
        if self.proxy.config.C16 < 0.3e-6:
            self.proxy.update_state(chip_load_range_margin=-1)

        self.proxy.turn_off_all_channels()
    
    @staticmethod
    def _capacitance_updated_wrapper(signal: dict[str, str]):
        capacitance = float(signal.get('new_value', 0.0)) * ureg.farad
        capacitance_formatted = f"{capacitance.to(ureg.picofarad):.4g~P}"
        voltage = float(signal.get('V_a', 0.0)) * ureg.volt
        voltage_formatted = f"{voltage:.3g~P}"
        publish_message(topic=CAPACITANCE_UPDATED,
                        message=json.dumps({'capacitance': capacitance_formatted, 'voltage': voltage_formatted}))

    @staticmethod
    def _shorts_detected_wrapper(signal: dict[str, str]):
        shorts_list = signal.get('values')
        shorts_dict = {'Shorts_detected': shorts_list}
        publish_message(topic=SHORTS_DETECTED, message=json.dumps(shorts_dict))

    @staticmethod
    def _halted_event_wrapper(signal):

        reason = ''

        if signal['error']['name'] == 'output-current-exceeded':
            reason = 'because output current was exceeded'
        elif signal['error']['name'] == 'chip-load-saturated':
            reason = 'because chip load feedback exceeded allowable range'

        # send out signal to all interested parties that the dropbot has been halted and request the HALT method
        publish_message(topic=HALTED, message=reason)
        publish_message(topic=HALT, message="")

        logger.error(f'DropBot halted due to {reason}')

    @staticmethod
    def _output_state_changed_wrapper(signal: dict[str, str]):
        if signal['event'] == 'output_enabled':
            logger.debug("Publishing Chip Inserted")
            publish_message(topic=CHIP_INSERTED, message='True')
        elif signal['event'] == 'output_disabled':
            logger.debug("Publishing Chip Not Inserted")
            publish_message(topic=CHIP_INSERTED, message='False')
        else:
            logger.warn(f"Unknown signal received: {signal}")

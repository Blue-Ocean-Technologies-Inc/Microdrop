from datetime import datetime

from traits.api import Instance, Dict
import dramatiq

# unit handling

from microdrop_utils.ureg_helpers import ureg
from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor, invoke_class_method, TimestampedMessage


from traits.api import HasTraits, provides, Bool, Str

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from .interfaces.i_peripheral_controller_base import IPeripheralControllerBase
from microdrop_utils.dramatiq_peripheral_serial_proxy import DramatiqPeripheralSerialProxy
from .preferences import PeripheralPreferences

from .consts import DEVICE_NAME, DISCONNECTED, CONNECTED, START_DEVICE_MONITORING, PKG

from logger.logger_service import get_logger
logger = get_logger(__name__, level="INFO")

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()


@provides(IPeripheralControllerBase)
class PeripheralControllerBase(HasTraits):
    """
    This class provides some methods for handling signals from the proxy. But mainly provides a dramatiq listener
    that captures appropriate signals and calls the methods needed.
    """
    proxy = Instance(DramatiqPeripheralSerialProxy)
    connection_active = Bool(False)
    preferences = Instance(PeripheralPreferences)
    _device_name = DEVICE_NAME

    ##########################################################
    # 'IDramatiqControllerBase' interface.
    ##########################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    listener_name = Str(f"{PKG}_listener")
    
    timestamps = Dict(str, datetime)

    def __del__(self):
        """Cleanup when the controller is destroyed."""
        self.cleanup()

    def cleanup(self):
        """Cleanup resources when the controller is stopped."""
        logger.info(f"Cleaning up {self._device_name.title()} Controller resources")
        if self.proxy is not None:
            try:
                self.proxy.terminate()
                logger.info(f"{self._device_name.title()} proxy terminated")
            except Exception as e:
                logger.error(f"Error terminating {self._device_name} proxy: {e}")
            finally:
                self.proxy = None
                self.connection_active = False

    def listener_actor_routine(self, timestamped_message: TimestampedMessage, topic: str):
        """
        A Dramatiq actor that listens to messages.

        Parameters:
        message (str): The received message.
        topic (str): The topic of the message.

        """
      
        logger.debug(f"{self._device_name.upper()} BACKEND LISTENER: Received message: '{timestamped_message}' from topic: {topic} at {timestamped_message.timestamp}")

        # find the topics hierarchy: first element is the head topic. Last element is the specific topic
        topics_tree = topic.split("/")
        head_topic = topics_tree[0]
        primary_sub_topic = topics_tree[1] #if len(topics_tree) > 1 else ""
        specific_sub_topic = topics_tree[-1]

        # set requested method to None for now
        requested_method = None

        # 1. Check if topic for this device
        if head_topic == self._device_name:

            # Handle the connected / disconnected signals
            if topic in [CONNECTED, DISCONNECTED]:
                if topic == CONNECTED:
                    self.connection_active = True
                else:
                    self.connection_active = False

            # 3. Handle exceptions:
            # specific  requests that would change connectivity
            # settings change (user preference)
            elif topic in [START_DEVICE_MONITORING]:
                requested_method = f"on_{specific_sub_topic}_request"
            
            # Handle all other requests only if connected
            elif primary_sub_topic == 'requests':
                if self.connection_active:
                    requested_method = f"on_{specific_sub_topic}_request"
                else:
                    logger.warning(f"Request for {specific_sub_topic} denied: {self._device_name} is disconnected.")

        else:
            logger.debug(f"Ignored request from topic '{topic}': Not a {self._device_name}-related request.")

        if requested_method:
            if self.timestamps.get(topic, datetime.min) > timestamped_message.timestamp_dt:
                logger.debug(f"{self._device_name.title()} Controller: Ignoring older message from topic: {topic} received at {timestamped_message.timestamp_dt}")
                return

            self.timestamps[topic] = timestamped_message.timestamp_dt
            
            err_msg = invoke_class_method(self, requested_method, timestamped_message)

            if err_msg:
                logger.error(
                    f" {self.listener_name}; Received message: {timestamped_message} from topic: {topic} Failed to execute due to "
                    f"error: {err_msg}")


    ### Initial traits values ######

    def traits_init(self):
        """
        This is equivalent to doing:

        def __init__(self, **traits):
            super().__init__(**traits)

        """
        logger.info(f"Starting {self._device_name.title()} Controller listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine)
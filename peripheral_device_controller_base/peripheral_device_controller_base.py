from datetime import datetime

import dramatiq
from traits.api import HasTraits, Any, Bool, Str, Dict, List, Instance, observe

from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
    invoke_class_method,
    TimestampedMessage,
)

from .consts import (
    DEFAULT_ALWAYS_ALLOWED_SUBTOPICS,
    connected_topic,
    disconnected_topic,
    connection_state_key,
)

from logger.logger_service import get_logger
logger = get_logger(__name__, level="INFO")

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()


class PeripheralDeviceControllerBase(HasTraits):
    """Generic backend controller for a serial peripheral device.

    Provides a Dramatiq listener that routes ``<device>/requests/...`` topics to
    ``on_<specific_sub_topic>_request`` methods and the connected/disconnected
    signals to ``on_<specific_sub_topic>_signal`` methods. Requests are processed
    only while the device is connected, except for the always-allowed subtopics
    (connection management).

    Subclasses MUST set:
        ``_device_name``  — e.g. ``"ZStage"`` / ``"Heater"``.
        ``listener_name`` — must equal the key in the plugin's ACTOR_TOPIC_DICT.
        ``proxy``         — narrow the type via ``Instance(<SpecificProxy>)``.
    """

    # --- device-specific knobs (set by subclasses) ---------------------------
    _device_name = Str()
    proxy = Any()
    listener_name = Str()
    _always_allowed_subtopics = List(Str, DEFAULT_ALWAYS_ALLOWED_SUBTOPICS)

    # --- generic state -------------------------------------------------------
    connection_active = Bool(False)
    timestamps = Dict(str, datetime)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    # --- derived topics ------------------------------------------------------
    @property
    def connected_topic(self):
        return connected_topic(self._device_name)

    @property
    def disconnected_topic(self):
        return disconnected_topic(self._device_name)

    @property
    def connection_state_key(self):
        return connection_state_key(self._device_name)

    ##########################################################
    # Lifecycle
    ##########################################################

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

    @observe("connection_active")
    def _mirror_connection_state_to_app_globals(self, event):
        """Mirror the connection state to app_globals so any plugin can read it
        synchronously without subscribing to the connected/disconnected signals."""
        app_globals[self.connection_state_key] = event.new
        logger.info(f"App Globals Update: {self.connection_state_key}: {event.new}")

    ##########################################################
    # Dramatiq listener
    ##########################################################

    def listener_actor_routine(self, timestamped_message: TimestampedMessage, topic: str):
        """A Dramatiq actor that listens to messages and dispatches them to the
        matching ``on_<sub>_request`` / ``on_<sub>_signal`` handler."""

        logger.debug(
            f"{self._device_name.upper()} BACKEND LISTENER: Received message: "
            f"'{timestamped_message}' from topic: {topic} at {timestamped_message.timestamp}")

        # find the topics hierarchy: first element is the head topic, last is the specific topic
        topics_tree = topic.split("/")
        head_topic = topics_tree[0]
        primary_sub_topic = topics_tree[1] if len(topics_tree) > 1 else ""
        specific_sub_topic = topics_tree[-1]

        requested_method = None

        # 1. Check if topic for this device
        if head_topic == self._device_name:

            # Handle the connected / disconnected signals
            if topic in (self.connected_topic, self.disconnected_topic):
                self.connection_active = (topic == self.connected_topic)
                requested_method = f"on_{specific_sub_topic}_signal"

            # Connection-management requests are allowed even while disconnected
            elif specific_sub_topic in self._always_allowed_subtopics:
                requested_method = f"on_{specific_sub_topic}_request"

            # All other requests only run if connected
            elif primary_sub_topic == 'requests':
                if self.connection_active:
                    requested_method = f"on_{specific_sub_topic}_request"
                else:
                    logger.warning(
                        f"Request for {specific_sub_topic} denied: {self._device_name} is disconnected.")

        else:
            logger.debug(f"Ignored request from topic '{topic}': Not a {self._device_name}-related request.")

        if requested_method:
            if self.timestamps.get(topic, datetime.min) > timestamped_message.timestamp_dt:
                logger.debug(
                    f"{self._device_name.title()} Controller: Ignoring older message from topic: "
                    f"{topic} received at {timestamped_message.timestamp_dt}")
                return

            self.timestamps[topic] = timestamped_message.timestamp_dt

            err_msg = invoke_class_method(self, requested_method, timestamped_message)

            if err_msg:
                logger.error(
                    f" {self.listener_name}; Received message: {timestamped_message} from topic: "
                    f"{topic} Failed to execute due to error: {err_msg}")

    def traits_init(self):
        """Equivalent to ``__init__`` calling ``super().__init__(**traits)``."""
        logger.info(f"Starting {self._device_name.title()} Controller listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine)

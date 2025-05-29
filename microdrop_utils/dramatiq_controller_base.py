import re
import traceback
import warnings
from typing import Any
from datetime import datetime


import dramatiq
from dramatiq import Actor
from dramatiq.middleware import CurrentMessage
from traits.api import Instance, Str, provides, HasTraits, Callable

from . import logger
from .i_dramatiq_controller_base import IDramatiqControllerBase
from .timestamped_message import TimestampedMessage


@provides(IDramatiqControllerBase)
class DramatiqControllerBase(HasTraits):
    """Base controller class for Dramatiq message handling.

    This class provides a framework for handling asynchronous messages using
    Dramatiq. It automatically sets up a listener actor that can process
    messages based on topics and routes them to appropriate handler methods.

    Attributes:
        listener_name (str): Name identifier for the Dramatiq actor
        listener_queue (str): The unique queue actor is listening to
        listener (Actor): Dramatiq actor instance for message processing

    Example:
        >>> class MyController(DramatiqControllerBase):
        ...     # Return a listener actor method if one is not provided
        ...     def _listener_actor_method_default(self, message: str,
        ...                                      topic: str) -> None:
        ...         def listener_actor_method(self, message: str,
        ...                                 topic: str) -> None:
        ...             print(f"Processing {message} from {topic}")
        ...         return listener_actor_method
        >>> dramatiq_controller = MyController()
        >>> def method():
        ...     return None
        >>> dramatiq_controller = DramatiqControllerBase(
        ...     listener_name=listener_name,
        ...     listener_actor_method=method
        ... )
        >>> dramatiq_controller.listener_actor.__class__
        >>> <class 'dramatiq.actor.Actor'>
    """

    listener_name = Str(desc="Unique identifier for the Dramatiq actor")
    listener_queue = Str("default", desc="The unique queue actor is listening to")
    listener_actor_method = Callable(
        desc="Routine to be wrapped into listener_actor. Should accept "
             "parent_obj, message, topic parameters"
    )
    listener_actor: Actor = Instance(
        Actor,
        desc="Dramatiq actor instance for message handling"
    )

    def traits_init(self) -> None:
        """Initialize the controller by setting up the Dramatiq listener."""
        if not self.listener_name:
            raise ValueError(
                "listener_name must be set before creating the actor"
            )

        if not self.listener_actor_method:
            raise ValueError(
                "listener_actor_method must be set before creating the actor"
            )

        self.listener_actor = self._listener_actor_default()

    def _listener_name_default(self):
        """Set the default listener actor name to be class name in snake_case."""
        class_name = self.__class__.__name__  # class name in camel case
        # convert to snake case
        class_name = re.sub(r'([a-z])([A-Z])', r'\1_\2', class_name).lower()
        return class_name

    def _listener_actor_default(self) -> Actor:
        """Create and configure the Dramatiq actor for message handling.

        Returns:
            Actor: Configured Dramatiq actor instance

        Note:
            The created actor will use the class's listener_name and
            route messages to the listener_routine method.
        """
        @dramatiq.actor(
            actor_name=self.listener_name,
            queue_name=self.listener_queue
        )
        def create_listener_actor(message: str, topic: str) -> None:
            """Handle incoming Dramatiq messages.

            Args:
                message: Content of the received message
                topic: Topic/routing key of the message
            """

            msg_proxy = CurrentMessage.get_current_message()
            msg_timestamp = (
                msg_proxy._message.message_timestamp if msg_proxy is not None
                else None
            )

            timestamped_message = TimestampedMessage( # Convert the message to a TimestampedMessage and propagate it to the listener_actor_method
                content=message,
                timestamp=msg_timestamp
            )
            self.listener_actor_method(timestamped_message, topic)

        return create_listener_actor


def generate_class_method_dramatiq_listener_actor(
    listener_name: str,
    class_method: Callable,
    listener_queue: str = "default"
) -> Actor:
    """Generate a Dramatiq Actor for message handling for a class method.

    Args:
        listener_name: Name identifier for the Dramatiq actor
        listener_queue: The unique queue actor is listening to
        class_method: Method that handles message handling to be wrapped as Actor

    Returns:
        Actor: Configured Dramatiq actor instance
    """
    # If the given listener name is not registered,
    if listener_name in dramatiq.get_broker().actors:
        warnings.warn(
            "Dramatiq actor with this name has already been registered. "
            "No need to create a new actor."
        )
    else:
        dramatiq_controller = DramatiqControllerBase(
            listener_name=listener_name,
            listener_actor_method=class_method,
            listener_queue=listener_queue
        )
        return dramatiq_controller.listener_actor


def basic_listener_actor_routine(
    parent_obj: object,
    message: Any,
    topic: str,
    handler_name_pattern: str = "_on_{topic}_triggered"
) -> None:
    """Dispatch incoming message to dynamically determined handler method.

    This function logs the received message and topic, derives a method name
    using the specified naming pattern, and checks if the parent object
    contains a callable method with that name. If so, it invokes the method
    with the message.

    Args:
        parent_obj: Object expected to have a handler method for the topic.
                   Should have a 'name' attribute used for logging.
        message: Message or data payload to be processed by handler method.
        topic: Topic string from which handler method name is derived.
               Expected to be a string with segments separated by "/".
        handler_name_pattern: Format string defining handler method's name.
                            Must include '{topic}' placeholder. Defaults to
                            "_on_{topic}_triggered".

    Example:
        For a topic "devices/sensor", the computed method name will be
        "_on_sensor_triggered".
    """
    msg_proxy = CurrentMessage.get_current_message()
    msg_timestamp = (
        msg_proxy._message.message_timestamp if msg_proxy is not None
        else None
    )

    timestamped_message = TimestampedMessage(
        content=message,
        timestamp=msg_timestamp
    )

    logger.info(
        f"{parent_obj.name}: Received message: '{timestamped_message}' "
        f"from topic: {topic} at {timestamped_message.timestamp}"
    )

    # Split the topic into parts and take the last segment as the key.
    topic_parts = topic.split("/")
    topic_key = topic_parts[-1]

    # Compute the handler method name using the provided pattern.
    requested_method = handler_name_pattern.format(topic=topic_key)

    err_msg = invoke_class_method(
        parent_obj,
        requested_method,
        timestamped_message
    )

    if err_msg:
        logger.error(
            f"{parent_obj.name}: Received message: {timestamped_message} "
            f"from topic: {topic} Failed to execute due to error: {err_msg}"
        )


def invoke_class_method(parent_obj, requested_method: str, *args, **kwargs):
    """Invoke a requested method defined within a parent object class.

    Args:
        parent_obj: Object containing the method to invoke
        requested_method: Name of the method to invoke
        *args: Positional arguments to pass to the method
        **kwargs: Keyword arguments to pass to the method

    Returns:
        str: Empty string if successful, error message if failed
    """
    error_msg = ""

    # check if parent obj has the requested method
    if hasattr(parent_obj, requested_method):
        class_method = getattr(parent_obj, requested_method)

        # Ensure that the attribute is callable before invoking it.
        if callable(class_method):
            # Invoke the requested method with the provided arguments and log any errors calling it
            try:
                class_method(*args, **kwargs)
                return error_msg
            except Exception as e:
                stack_trace = traceback.format_exc()
                error_msg = (
                    f"Error executing '{requested_method}': "
                    f"\nArguments: {args, kwargs}\n {stack_trace}"
                )
                logger.error(error_msg)
                return error_msg
        else:
            error_msg = (
                f"{parent_obj}: Attribute '{requested_method}' "
                "exists but is not callable."
            )
            logger.warning(error_msg)
            return error_msg
    else:
        error_msg = f"Method '{requested_method}' not found for {parent_obj}."
        logger.warning(error_msg)
        return error_msg


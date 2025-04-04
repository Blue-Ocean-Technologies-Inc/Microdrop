import warnings

import dramatiq
from dramatiq import Actor
from traits.api import Instance, Str, provides, HasTraits, Callable

from . import logger
from .i_dramatiq_controller_base import IDramatiqControllerBase


@provides(IDramatiqControllerBase)
class DramatiqControllerBase(HasTraits):
    """Base controller class for Dramatiq message handling.

    This class provides a framework for handling asynchronous messages using Dramatiq.
    It automatically sets up a listener actor that can process messages based on topics
    and routes them to appropriate handler methods.

    Attributes:
        listener_name (str): Name identifier for the Dramatiq actor
        listener (Actor): Dramatiq actor instance that handles message processing

    Example:
        >>> class MyController(DramatiqControllerBase):
        ...     listener_name = "my_listener"
        ...
        ...     def listener_actor_routine(parent_obj, message: str, topic: str) -> None:
        ...         print(f"Processing {message} from {topic}")

        >>> dramatiq_controller = DramatiqControllerBase(listener_name=listener_name, listener_actor_routine=method)
        >>> dramatiq_controller.listener_actor.__class__
        >>> <class 'dramatiq.actor.Actor'>
    """

    listener_name: str = Str(desc="Unique identifier for the Dramatiq actor")
    listener_actor_method = Callable(desc="Routine to be wrapped into listener_actor"
                                           "Should accept parent_obj, message, topic parameters")
    listener_actor: Actor = Instance(Actor, desc="Dramatiq actor instance for message handling")

    def traits_init(self) -> None:
        """Initialize the controller by setting up the Dramatiq listener.

        This method is called during object initialization and sets up the
        Dramatiq actor using the configuration specified in _listener_default.
        """

        if not self.listener_name:
            raise ValueError("listener_name must be set before creating the actor")

        if not self.listener_actor_method:
            raise ValueError("listener_actor_method must be set before creating the actor")

        self.listener_actor = self._listener_actor_default()

    def _listener_actor_default(self) -> Actor:
        """Create and configure the Dramatiq actor for message handling.

        Returns:
            Actor: Configured Dramatiq actor instance

        Note:
            The created actor will use the class's listener_name and
            route messages to the listener_routine method.
        """

        @dramatiq.actor(actor_name=self.listener_name)
        def create_listener_actor(message: str, topic: str) -> None:
            """Handle incoming Dramatiq messages.

            Args:
                parent_obj: Parent class this listener actor should belong to and control.
                message: Content of the received message
                topic: Topic/routing key of the message
            """
            self.listener_actor_method(message, topic)

        return create_listener_actor


def generate_class_method_dramatiq_listener_actor(listener_name, class_method) -> Actor:
    """
    Method to generate a Dramatiq Actor for message handling for a class based on one of its methods.

    Params:
    listener_name (str): Name identifier for the Dramatiq actor.
    class_method (Callable): Method that handles message handling that requires to be wrapped up as an Actor
    """
    # If the given listener name is not registered,
    if listener_name in dramatiq.get_broker().actors:
        warnings.warn("Dramatiq actor with this name has already been registered.This plugin already has a listener "
                        "actor. No need to create a new actor.")

    else:

        # Dramatiq controller base class made  with listener actor generated as an attribute
        dramatiq_controller = DramatiqControllerBase(listener_name=listener_name, listener_actor_method=class_method)

        return dramatiq_controller.listener_actor


def basic_listener_actor_routine(parent_obj: object, message: any, topic: str,
                                 handler_name_pattern: str = "_on_{topic}_triggered") -> None:
    """
    Dispatches an incoming message to a dynamically determined handler method on the parent object.

    This function logs the received message and topic, derives a method name using the specified
    naming pattern (defaulting to "_on_{topic}_triggered"), and then checks if the parent object
    contains a callable method with that name. If so, it invokes the method with the message.

    Parameters:
        parent_obj (object): The object expected to have a handler method for the given topic.
                             It is assumed that parent_obj has a 'name' attribute used for logging.
        message (any): The message or data payload to be processed by the handler method.
        topic (str): The topic string from which the handler method name is derived.
                     The topic is expected to be a string containing segments separated by "/".
        handler_name_pattern (str, optional): A format string that defines the handler method's name.
                     It must include a placeholder '{topic}', which will be replaced by the last segment
                     of the provided topic. Defaults to "_on_{topic}_triggered".

    Example:
        For a topic "devices/sensor", the computed method name will be "_on_sensor_triggered".

    Returns:
        None
    """
    logger.info(f"{parent_obj.name}: Received message: {message} from topic: {topic}")

    # Split the topic into parts and take the last segment as the key.
    topic_parts = topic.split("/")
    topic_key = topic_parts[-1]

    # Compute the handler method name using the provided pattern.
    requested_method = handler_name_pattern.format(topic=topic_key)

    # invoke the method, and check if any error_message shows up
    err_msg = invoke_class_method(parent_obj, requested_method, message)

    if err_msg:
        logger.error(f"{parent_obj.name}: Received message: {message} from topic: {topic} Failed to execute due to "
                     f"error: {err_msg}")


def invoke_class_method(parent_obj, requested_method: str, *args, **kwargs):
    """
    Method to invoke a requested method that could be defined within a parent object class with some arguments
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
                error_msg = f"Error executing '{requested_method}': \nArguments: {args, kwargs}\n Exception: {e}"
                logger.error(error_msg)
                return error_msg
        # log a warning if the requested method is an attribute but not a callable
        else:
            error_msg = f"{parent_obj}: Attribute '{requested_method}' exists but is not callable."
            logger.warning(error_msg)
            return error_msg

    else:
        error_msg = f"Method '{requested_method}' not found for {parent_obj}."
        logger.warning(error_msg)
        return error_msg

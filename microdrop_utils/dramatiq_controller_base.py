# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import re
import traceback
import warnings

import dramatiq
from dramatiq import Actor
from dramatiq.middleware import CurrentMessage

from traits.api import Callable, HasTraits, Instance, Str, provides

from .datetime_helpers import TimestampedMessage
from .i_dramatiq_controller_base import IDramatiqControllerBase

from logger.logger_service import debug_throttled, get_logger

logger = get_logger(__name__)


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
        ...     def _listener_actor_method_default(self):
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
        Actor, desc="Dramatiq actor instance for message handling"
    )

    def traits_init(self) -> None:
        """Initialize the controller by setting up the Dramatiq listener."""
        if not self.listener_name:
            raise ValueError("listener_name must be set before creating the actor")

        if not self.listener_actor_method:
            raise ValueError(
                "listener_actor_method must be set before creating the actor"
            )

        self.listener_actor = self._listener_actor_default()

    def _listener_name_default(self):
        """Set the default listener actor name to be class name in snake_case."""
        class_name = self.__class__.__name__  # class name in camel case
        # convert to snake case
        class_name = re.sub(r"([a-z])([A-Z])", r"\1_\2", class_name).lower()
        return class_name

    def _listener_actor_default(self) -> Actor:
        """Create and configure the Dramatiq actor for message handling.

        Returns:
            Actor: Configured Dramatiq actor instance

        Note:
            The created actor will use the class's listener_name and
            route messages to the listener_routine method.
        """

        @dramatiq.actor(actor_name=self.listener_name, queue_name=self.listener_queue)
        def create_listener_actor(
            message: str, topic: str, timestamp: float | None = None
        ) -> None:
            """Handle incoming Dramatiq messages.

            Args:
                message: Content of the received message
                topic: Topic/routing key of the message
                timestamp: Timestamp of the message. If None, the timestamp
                    is extracted from the current message.
            """
            if timestamp is None:  # This is the message *to* the message_router
                msg_proxy = CurrentMessage.get_current_message()
                msg_timestamp = (
                    msg_proxy._message.message_timestamp
                    if msg_proxy is not None
                    else None
                )
                debug_throttled(
                    logger,
                    f"to_router:{topic}",
                    f"Message going to message_router: {message} at {msg_timestamp}",
                )
            else:  # This is the message *from* the message_router (since
                # message_router is the only publish_message that adds a
                # timestamp)
                msg_timestamp = timestamp
                debug_throttled(
                    logger,
                    f"from_router:{topic}",
                    f"Message received from message_router: {message} at "
                    f"{msg_timestamp}",
                )

            # Convert the message to a TimestampedMessage and propagate it
            # to the listener_actor_method
            timestamped_message = TimestampedMessage(
                content=message, timestamp=msg_timestamp
            )
            self.listener_actor_method(timestamped_message, topic)

        return create_listener_actor


def generate_class_method_dramatiq_listener_actor(
    listener_name: str,
    class_method: Callable,
    listener_queue: str = "default",
    topics=None,
    handler_name_pattern: str = "_on_{topic}_triggered",
) -> Actor:
    """Generate a Dramatiq Actor for message handling for a class method.

    Args:
        listener_name: Name identifier for the Dramatiq actor
        listener_queue: The unique queue actor is listening to
        class_method: Method that handles message handling to be wrapped as Actor
        topics: The listener's subscribed topics (typically
            ACTOR_TOPIC_DICT[listener_name]). When given, runs
            assert_handlers_exist_for_topics against class_method.__self__
            once at registration, so a typo'd or renamed handler fails at
            app start instead of silently.
        handler_name_pattern: Forwarded to assert_handlers_exist_for_topics.

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
        if topics:
            assert_handlers_exist_for_topics(
                class_method.__self__, topics, handler_name_pattern=handler_name_pattern
            )

        dramatiq_controller = DramatiqControllerBase(
            listener_name=listener_name,
            listener_actor_method=class_method,
            listener_queue=listener_queue,
        )
        return dramatiq_controller.listener_actor


def unregister_dramatiq_listener_actor(listener_name: str) -> bool:
    """Remove a listener actor from the broker's registry.

    The inverse of generate_class_method_dramatiq_listener_actor, needed for
    runtime hot unload/reload: while the name stays registered, a re-mount's
    generate call warns and returns None, and the stale actor keeps dispatching
    to the old, torn-down handler instance. Dramatiq has no public
    remove-actor API, so this pops the broker's actor registry directly.

    Returns True if an actor was removed, False if none was registered.
    """
    actor = dramatiq.get_broker().actors.pop(listener_name, None)
    if actor is None:
        logger.debug(f"No dramatiq actor named {listener_name!r} to unregister")
        return False
    logger.info(f"Unregistered dramatiq actor {listener_name!r}")
    return True


def is_wildcard_topic(topic: str) -> bool:
    """True if topic is an MQTT-style subscription pattern ('+' or '#').

    A wildcard entry in an ACTOR_TOPIC_DICT matches many concrete topics at
    once, so it cannot be resolved to a single handler method name.
    """
    return "+" in topic or topic.endswith("#")


def resolve_handler_name(
    topic: str, handler_name_pattern: str = "_on_{topic}_triggered"
) -> str:
    """Derive the reflective handler method name for a topic.

    Takes the topic's last "/"-delimited segment as the key and formats it
    into handler_name_pattern. This is the SAME transformation used by
    basic_listener_actor_routine at message time and by
    assert_handlers_exist_for_topics at startup, so dispatch and the startup
    check cannot drift apart.

    Example:
        For a topic "devices/sensor", the computed method name will be
        "_on_sensor_triggered".
    """
    topic_key = topic.split("/")[-1]
    return handler_name_pattern.format(topic=topic_key)


def basic_listener_actor_routine(
    parent_obj: object,
    timestamped_message: TimestampedMessage,
    topic: str,
    handler_name_pattern: str = "_on_{topic}_triggered",
) -> None:
    """Dispatch incoming message to dynamically determined handler method.

    This function logs the received message and topic, derives a method name
    using the specified naming pattern, and checks if the parent object
    contains a callable method with that name. If so, it invokes the method
    with the message.

    Args:
        parent_obj: Object expected to have a handler method for the topic.
                   Should have a 'name' attribute used for logging.
        timestamped_message: TimestampedMessage object containing the
                   message and timestamp.
        topic: Topic string from which handler method name is derived.
               Expected to be a string with segments separated by "/".
        handler_name_pattern: Format string defining handler method's name.
                            Must include '{topic}' placeholder. Defaults to
                            "_on_{topic}_triggered".

    Example:
        For a topic "devices/sensor", the computed method name will be
        "_on_sensor_triggered".
    """

    # Debug level: at info this printed EVERY routed message (the old code
    # hand-excluded the two chattiest topics; at debug no exclusion needed).
    # Throttled per (listener, topic): streaming topics fire many times a second.
    debug_throttled(
        logger,
        f"listener_rx:{parent_obj.name}:{topic}",
        f"{parent_obj.name}: Received message: '{timestamped_message}' "
        f"from topic: {topic} at {timestamped_message.timestamp}",
    )

    # Compute the handler method name using the provided pattern.
    requested_method = resolve_handler_name(topic, handler_name_pattern)

    err_msg = invoke_class_method(parent_obj, requested_method, timestamped_message)

    if err_msg:
        logger.error(
            f"{parent_obj.name}: Received message: {timestamped_message} "
            f"from topic: {topic} Failed to execute due to error: {err_msg}"
        )


def assert_handlers_exist_for_topics(
    parent_obj: object,
    topics,
    handler_name_resolver: Callable = None,
    handler_name_pattern: str = "_on_{topic}_triggered",
    raise_on_missing: bool = True,
) -> None:
    """Startup check: every subscribed topic must resolve to a real handler.

    Applies the SAME topic->handler-name transformation dispatch uses
    (resolve_handler_name by default, or handler_name_resolver for
    controllers with custom routing, e.g. DropbotControllerBase's
    signal/request split) so this check can never drift from what dispatch
    actually does. Meant to be called once per controller instance at
    listener registration, not per message.

    Wildcard topics ('+' / a trailing '#') subscribe to many concrete topics
    at once and cannot be resolved to a single handler name, so they are
    skipped (debug log) — a controller relying on wildcard dispatch handles
    those through its own listener_actor_routine, not reflectively here.
    A resolver may also return None for a topic it deliberately handles as
    a non-reflective side effect; that topic is skipped too.

    Raises AttributeError listing every mismatch when raise_on_missing is
    True (the default); otherwise logs each mismatch via logger.error so a
    known legacy exception doesn't block startup.
    """
    resolver = handler_name_resolver or (
        lambda topic: resolve_handler_name(topic, handler_name_pattern)
    )

    missing = []
    for topic in topics:
        if is_wildcard_topic(topic):
            logger.debug(f"Skipping wildcard topic in handler check: {topic}")
            continue

        handler_name = resolver(topic)
        if handler_name is None:
            continue

        if not callable(getattr(parent_obj, handler_name, None)):
            missing.append(f"{topic!r} -> {handler_name}()")

    if missing:
        message = (
            f"{parent_obj}: no handler method found for subscribed topic(s): "
            f"{'; '.join(missing)}. Check for a typo in the handler method "
            "name or a stale ACTOR_TOPIC_DICT entry."
        )
        if raise_on_missing:
            raise AttributeError(message)
        logger.error(message)


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
            # Invoke the requested method with the provided arguments and
            # log any errors calling it
            try:
                class_method(*args, **kwargs)
                return error_msg
            except Exception:
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

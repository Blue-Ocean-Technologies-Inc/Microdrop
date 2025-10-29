from dramatiq import Actor
from traits.api import Interface, Instance, Str, Callable, Subclass


class IDramatiqControllerBase(Interface):
    """
    Interface for some controller.
    Provides methods for controlling some object via dramatiq signalling.
    """

    listener_name = Str(desc="Unique identifier for the Dramatiq actor")
    listener_queue = Str(desc="The unique queue actor is listening to")
    listener_actor = Instance(Actor, desc="Dramatiq actor instance for message handling")
    listener_actor_method = Callable(desc="Method to be wrapped into listener_actor"
                                          "Should accept message, topic parameters")

    def traits_init(self):
        """
        Initialize the controller: Automatically Sets listener actor returned by _listener_default.

        Do not have to event do anything in this method. Just needs to pass.

        Could set the listener explicitly for clarity.
        """
        pass

    def _listener_actor_default(self) -> Actor:
        """
        Wraps up listener routine as a dramatiq actor and returns it.

        Returns:
        dramatiq.Actor: The created Dramatiq actor.
        """
        pass

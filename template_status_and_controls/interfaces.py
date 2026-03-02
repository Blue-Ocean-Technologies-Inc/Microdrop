"""
Formal interface contracts for the status-and-controls template.

Using traits.api.Interface lets the traits type system enforce that
components satisfy a contract when composed together (e.g. the model
passed to a message handler must provide IStatusModel).

Usage:
    from traits.api import provides

    @provides(IStatusModel)
    class MyModel(HasTraits):
        ...
"""

from traits.api import Interface, Bool, Str


class IStatusModel(Interface):
    """
    Contract that every device status model must satisfy.

    These are the traits the base controller, message handler, and dock pane
    depend on. Device-specific sensor traits are added on top in the subclass.
    """

    # ---- Mode flags (user-controllable) ----
    realtime_mode: bool     # send hardware updates continuously
    protocol_running: bool  # a protocol is currently executing
    free_mode: bool         # device is in free/manual mode

    # ---- Connection state (set by the message handler) ----
    connected: bool
    chip_inserted: bool

    # ---- Display traits (derived; updated by observers) ----
    connection_status_text: str
    icon_path: str
    icon_color: str


class IMessageHandler(Interface):
    """
    Contract for Dramatiq-backed message handlers.

    The handler subscribes to pub/sub topics and updates the model.
    It must be started (Dramatiq actor registered) via traits_init().
    """
    pass


class IStatusController(Interface):
    """
    Contract for TraitsUI controllers.

    The controller bridges UI interactions to pub/sub messages.
    It must expose publish_queued_messages() so queued changes
    can be flushed when the device enters realtime mode.
    """

    def publish_queued_messages(self) -> None:
        """Send all messages that were queued while not in realtime mode."""
        ...

"""
BaseMessageHandler — shared Dramatiq listener setup and common handlers.

This class owns the Dramatiq actor that receives pub/sub messages and
dispatches them to _on_<sub_topic>_triggered() methods via
basic_listener_actor_routine (reflection-based dispatch).

Shared handlers cover the topics every device sends:
  - connected / disconnected
  - realtime_mode_updated
  - protocol_running
  - display_state

Device-specific handlers (temperature, capacitance, shorts, …) are added
by overriding in the concrete subclass.

Design notes:
  - TimestampedMessage guards on connected_message and realtime_mode_message
    prevent stale out-of-order messages from reverting newer state.
  - The model attribute is typed as HasTraits (rather than the IStatusModel
    interface) to avoid circular-import issues at module level; callers should
    still pass a model that implements IStatusModel.
"""

import json

import dramatiq
from traits.api import HasTraits, Instance, Str, provides

from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)
from logger.logger_service import get_logger

from .interfaces import IMessageHandler

logger = get_logger(__name__)


@provides(IMessageHandler)
class BaseMessageHandler(HasTraits):
    """
    Shared Dramatiq listener setup and common pub/sub message handlers.

    Subclasses add device-specific _on_*_triggered() handlers and any
    extra internal state they need (e.g. capacitance averaging buffers).
    """

    # ---- Composition inputs ----
    model = Instance(HasTraits)          # must satisfy IStatusModel
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = Str()                         # unique listener name for Dramatiq

    # ---- Deduplication guards ----
    # TimestampedMessage lets @timestamped_value drop stale out-of-order msgs.
    connected_message = Instance(TimestampedMessage)
    realtime_mode_message = Instance(TimestampedMessage)

    def _connected_message_default(self):
        return TimestampedMessage("", 0)

    def _realtime_mode_message_default(self):
        return TimestampedMessage("", 0)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def traits_init(self):
        """Register the Dramatiq actor that feeds pub/sub messages to us."""
        logger.info(f"Starting message listener: {self.name!r}")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.name,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        """
        Entry point called by Dramatiq for every received message.

        basic_listener_actor_routine uses the topic's last path segment to
        find and call the matching _on_<segment>_triggered() method on self.
        """
        return basic_listener_actor_routine(self, message, topic)

    # ------------------------------------------------------------------ #
    # Common handlers — shared by every device                             #
    # ------------------------------------------------------------------ #

    @timestamped_value("connected_message")
    def _on_connected_triggered(self, body):
        logger.debug("Device connected")
        self.model.connected = True

    @timestamped_value("connected_message")
    def _on_disconnected_triggered(self, body):
        logger.debug("Device disconnected")
        self.model.connected = False
        # Force realtime mode off so the UI reflects the hardware state.
        self._on_realtime_mode_updated_triggered(
            TimestampedMessage("False", None), force_update=True
        )

    @timestamped_value("realtime_mode_message")
    def _on_realtime_mode_updated_triggered(self, body):
        realtime = body == "True"
        logger.debug(f"Realtime mode → {realtime}")
        self.model.realtime_mode = realtime

    def _on_protocol_running_triggered(self, message):
        self.model.protocol_running = message.casefold() == "true"

    def _on_display_state_triggered(self, message):
        self.model.free_mode = json.loads(message).get("free_mode")

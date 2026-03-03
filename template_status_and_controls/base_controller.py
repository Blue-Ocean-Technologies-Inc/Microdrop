"""
BaseStatusController — shared controller logic for all device panels.

Responsibilities:
  1. Message queueing: when not in realtime mode, the latest value for each
     topic is stored and flushed when realtime mode is enabled.
  2. Realtime mode toggle: publishes SET_REALTIME_MODE and flushes the queue.
  3. Debounced setattr for the realtime-mode checkbox.

Device-specific controllers extend this class and add observers for their
own hardware traits (voltage, frequency, …).

Design notes:
  - publish_queued_messages() is part of the IStatusController contract so
    that external code (e.g. the dock pane) can flush without knowing which
    concrete subclass is in use.
  - The message_dict stores only the *latest* value per topic, so rapid user
    input collapses to a single hardware command on flush.
"""

import functools

from traits.api import Dict, observe, provides
from traitsui.api import Controller

from dropbot_controller.consts import SET_REALTIME_MODE
from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from .interfaces import IStatusController

logger = get_logger(__name__)


@provides(IStatusController)
class BaseStatusController(Controller):
    """
    Shared controller: message queueing + realtime mode handling.

    Extend and add @observe handlers for device-specific traits.
    """

    # Maps topic -> functools.partial(publish_message, topic=…, message=…).
    # Only the last value queued per topic is kept, preventing stale commands.
    message_dict = Dict()

    # ------------------------------------------------------------------ #
    # IStatusController                                                    #
    # ------------------------------------------------------------------ #

    def publish_queued_messages(self):
        """
        Send the most-recently-queued message for each topic.

        Called automatically when the device enters realtime mode, so any
        slider/spinbox changes made while the device was offline are applied.
        """
        if not self.message_dict:
            logger.debug("Message queue is empty — nothing to flush")
            return

        tasks = list(self.message_dict.values())
        self.message_dict.clear()

        for task in tasks:
            try:
                task()
            except Exception as exc:
                logger.warning(f"Failed to publish queued message: {exc}")

    # ------------------------------------------------------------------ #
    # Protected helper                                                      #
    # ------------------------------------------------------------------ #

    def _publish_or_queue(self, topic: str, message: str) -> bool:
        """
        Publish immediately if in realtime mode; queue the value otherwise.

        Returns True when the message was published right away.
        """
        if self.model.realtime_mode:
            publish_message(topic=topic, message=message)
            return True

        # Overwrite any previous value for this topic — only the latest matters.
        self.message_dict[topic] = functools.partial(
            publish_message, topic=topic, message=message
        )
        logger.debug(f"Queued topic='{topic}' message='{message}' (not in realtime mode)")
        return False

    # ------------------------------------------------------------------ #
    # TraitsUI Controller interface — debounced setattr                    #
    # ------------------------------------------------------------------ #

    @debounce(wait_seconds=1)
    def realtime_mode_setattr(self, info, obj, traitname, value):
        """
        Debounced setter for the realtime-mode checkbox.

        The debounce prevents rapid toggle events from flooding the hardware
        with connect/disconnect commands.
        """
        # Keep the checkbox UI in sync (the debounce runs on a background
        # thread, so update_editor() won't be called automatically).
        info.realtime_mode.control.setChecked(value)
        return super().setattr(info, obj, traitname, value)

    # ------------------------------------------------------------------ #
    # Observers                                                             #
    # ------------------------------------------------------------------ #

    @observe("model:realtime_mode")
    def _on_realtime_mode_changed(self, event):
        """Publish the new realtime-mode state and flush the queue if enabled."""
        publish_message(topic=SET_REALTIME_MODE, message=str(event.new))
        if event.new:
            self.publish_queued_messages()

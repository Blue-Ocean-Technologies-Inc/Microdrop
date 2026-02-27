import functools

from traits.api import observe, Dict
from traitsui.api import (
    Controller,
)

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.decorators import debounce

from dropbot_controller.consts import (
    SET_VOLTAGE,
    SET_FREQUENCY,
    SET_REALTIME_MODE,
)

logger = get_logger(__name__)

class ControlsController(Controller):
    # Use a dict to store the *latest* task for each topic
    message_dict = Dict()

    def _publish_message_if_realtime(self, topic: str, message: str) -> bool:
        if self.model.realtime_mode:
            publish_message(topic=topic, message=message)
            return True
        else:
            # Create the task "snapshot"
            task = functools.partial(publish_message, topic=topic, message=message)
            logger.debug(
                f"QUEUEING Topic='{topic}, message={message}' when realtime mode on"
            )
            # Store the task, overwriting any previous task for this topic
            self.message_dict[topic] = task

        return False

    def publish_queued_messages(self):
        """Processes the most recent message for each topic."""
        logger.info(
            "\n--- Dropbot Controls: Publishing Queued Messages (Last Value Only) ---"
        )

        if not self.message_dict:
            logger.info("--- Dropbot Controls Queue empty ---")
            return

        # Get all the "latest" tasks that are waiting
        tasks_to_run = list(self.message_dict.values())
        # Clear the dict for the next batch
        self.message_dict.clear()

        for task in tasks_to_run:
            try:
                task()  # This executes: publish_message(topic=..., message=...)
            except Exception as e:
                logger.warning(f"Error publishing queued message: {e}")

    ###################################################################################
    # Controller interface — debounced setattr
    ###################################################################################

    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, object, traitname, value):
        return super().setattr(info, object, traitname, value)

    # This callback will not call update_editor() when it is not debounced!
    # This is likely because update_editor is only called by 'external' trait changes, and the new thread spawned by the decorator appears as such
    @debounce(wait_seconds=1)
    def realtime_mode_setattr(self, info, object, traitname, value):
        logger.debug(f"Set realtime mode to {value}")
        info.realtime_mode.control.setChecked(value)
        return super().setattr(info, object, traitname, value)

    ###################################################################################
    # Trait notification handlers
    ###################################################################################

    @observe("model:realtime_mode")
    def _realtime_mode_changed(self, event):
        publish_message(topic=SET_REALTIME_MODE, message=str(event.new))

        if event.new:
            self.publish_queued_messages()

    @observe("model:voltage")
    def _voltage_changed(self, event):
        if self._publish_message_if_realtime(topic=SET_VOLTAGE, message=str(event.new)):
            logger.debug(f"Requesting Voltage change to {event.new} V")

    @observe("model:frequency")
    def _frequency_changed(self, event):
        if self._publish_message_if_realtime(
            topic=SET_FREQUENCY, message=str(event.new)
        ):
            logger.debug(f"Requesting Frequency change to {event.new} Hz")
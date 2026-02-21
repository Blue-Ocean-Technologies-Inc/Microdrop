import json

import dramatiq
from traits.api import HasTraits, Instance, Str, provides

from logger.logger_service import get_logger
from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
    invoke_class_method,
)

from .dramatiq_UI import DramatiqOpenDropStatusViewModel
from .interfaces.i_dramatiq_opendrop_status_controller import IDramatiqOpenDropStatusController

logger = get_logger(__name__)


@provides(IDramatiqOpenDropStatusController)
class DramatiqOpenDropStatusController(HasTraits):
    """Hook OpenDrop status widget updates to dramatiq topics."""

    ui = Instance(DramatiqOpenDropStatusViewModel)

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = Str(desc="Unique identifier for the Dramatiq actor")

    def listener_actor_routine(self, message: TimestampedMessage, topic):
        logger.debug(
            f"UI_LISTENER: Received message: {message} from topic: {topic} at {message.timestamp}. Triggering UI signal."
        )
        try:
            self.controller_signal_handler(json.dumps({"message": message.serialize(), "topic": topic}))
        except RuntimeError as exc:
            if "Signal source has been deleted" in str(exc):
                logger.warning("View has been deleted, stopping signal emission")
            else:
                raise

    def traits_init(self):
        logger.info(f"Starting OpenDrop status listener: {self.listener_name}")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )

    def controller_signal_handler(self, signal):
        signal = json.loads(signal)
        topic = signal.get("topic", "")
        message_serialized = signal.get("message", "")
        message = TimestampedMessage.deserialize(message_serialized)

        head_topic = topic.split("/")[-1]
        method = f"_on_{head_topic}_triggered"

        err_msg = invoke_class_method(self.ui, method, message)
        if err_msg:
            logger.debug(f"No handler for topic '{topic}' ({method}): {err_msg}")

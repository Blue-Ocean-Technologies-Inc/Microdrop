import json

import dramatiq
from traits.api import HasTraits, Instance, Str

from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor
)

from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.decorators import timestamped_value

from .model import OpendropStatusAndControlsModel

from logger.logger_service import get_logger
logger = get_logger(__name__)


class OpendropStatusAndControlsMessageHandler(HasTraits):
    """Unified Dramatiq message handler for dropbot status and controls.

    Subscribes to dropbot/signals/# and ui/calibration_data.
    Updates the shared model and emits dialog signals.
    """

    model = Instance(OpendropStatusAndControlsModel)

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = Str()

    # TimestampedMessage helpers for deduplication
    realtime_mode_message = Instance(TimestampedMessage)
    connected_message = Instance(TimestampedMessage)

    def _realtime_mode_message_default(self):
        return TimestampedMessage("", 0)

    def _connected_message_default(self):
        return TimestampedMessage("", 0)

    def traits_init(self):
        logger.info(f"Starting {self.name} listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.name,
            class_method=self.listener_actor_routine)

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    ###########################################################################
    # Subscriber / handler methods (_on_*_triggered)
    ###########################################################################

    @timestamped_value('connected_message')
    def _on_connected_triggered(self, body):
        logger.debug("Connected to dropbot")
        self.model.connected = True

    @timestamped_value('connected_message')
    def _on_disconnected_triggered(self, body):
        logger.debug("Disconnected from dropbot")
        self.model.connected = False
        # Force realtime mode off on disconnect
        self._on_realtime_mode_updated_triggered(TimestampedMessage("False", None), force_update=True)

    @timestamped_value('realtime_mode_message')
    def _on_realtime_mode_updated_triggered(self, body):
        realtime = body == 'True'
        logger.debug(f"Realtime mode updated to {realtime}")
        self.model.realtime_mode = realtime

    def _on_board_info_triggered(self, body):
        data = json.loads(str(body))
        self.model.board_id = str(data.get("board_id", "-"))

    def _on_temperatures_updated_triggered(self, body):
        data = json.loads(str(body))
        t1 = data.get("t1")
        t2 = data.get("t2")
        t3 = data.get("t3")

        self.model.temperature_1 = "-" if t1 is None else f"{float(t1):.3f} C"
        self.model.temperature_2 = "-" if t2 is None else f"{float(t2):.3f} C"
        self.model.temperature_3 = "-" if t3 is None else f"{float(t3):.3f} C"

    def _on_feedback_updated_triggered(self, body):
        data = json.loads(str(body))
        active_channels = data.get("active_channels", "-")
        self.model.feedback_active_channels = str(active_channels)
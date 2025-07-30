import dramatiq

from traits.api import HasTraits, Str, Instance
from PySide6.QtCore import Signal, QObject

from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor
from microdrop_utils._logger import get_logger
from dropbot_controller.consts import DROPBOT_DISCONNECTED, CHIP_INSERTED, DROPBOT_CONNECTED
from protocol_grid.consts import DEVICE_VIEWER_STATE_CHANGED

logger = get_logger(__name__)


class MessageListenerSignalEmitter(QObject):
    device_viewer_message_received = Signal(str, str)  # message, topic
    dropbot_connection_changed = Signal(bool)  # dropbot connection status


class MessageListener(HasTraits):
    """
    Listens for messages and emits a Qt signal.
    """
    signal_emitter = Instance(MessageListenerSignalEmitter)
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = Str("protocol_grid_message_listener")

    def __init__(self, **traits):
        super().__init__(**traits)
        self.signal_emitter = MessageListenerSignalEmitter()
        self.traits_init()

    def listener_actor_routine(self, message, topic):
        try:
            if topic == DEVICE_VIEWER_STATE_CHANGED:
                logger.info(f"Received device viewer message on topic: {topic}")
                self.signal_emitter.device_viewer_message_received.emit(message, topic)
                
            elif topic in [CHIP_INSERTED, DROPBOT_CONNECTED]:
                logger.info(f"Received dropbot connected signal: {topic}")
                self.signal_emitter.dropbot_connection_changed.emit(True)
                
            elif topic == DROPBOT_DISCONNECTED:
                logger.info(f"Received dropbot disconnected signal: {topic}")
                self.signal_emitter.dropbot_connection_changed.emit(False)
                
            else:
                logger.info(f"Unhandled message topic: {topic}")
                
        except Exception as e:
            logger.info(f"Error handling message on topic {topic}: {e}")

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine
        )
        logger.info(f"Message listener initialized: {self.listener_name}")
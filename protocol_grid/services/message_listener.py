import dramatiq

from traits.api import HasTraits, Str, Instance
from PySide6.QtCore import Signal, QObject

from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor
from microdrop_utils._logger import get_logger
from dropbot_controller.consts import (DROPBOT_DISCONNECTED, CHIP_INSERTED,
                                       DROPBOT_CONNECTED, DROPLETS_DETECTED,
                                       CAPACITANCE_UPDATED)
from protocol_grid.consts import (DEVICE_VIEWER_STATE_CHANGED, PROTOCOL_GRID_LISTENER_NAME,
                                  CALIBRATION_DATA)

logger = get_logger(__name__)


class MessageListenerSignalEmitter(QObject):
    device_viewer_message_received = Signal(str, str)  # message, topic
    dropbot_connection_changed = Signal(bool)  # dropbot connection status
    droplets_detected = Signal(str)  # droplet detection response
    calibration_data_received = Signal(str, str)  # message, topic
    capacitance_updated = Signal(str) # capacitance updated signal -> CAPACITANCE_UPDATED message


class MessageListener(HasTraits):
    """
    Listens for messages and emits a Qt signal.
    """
    signal_emitter = Instance(MessageListenerSignalEmitter)
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = PROTOCOL_GRID_LISTENER_NAME

    def __init__(self, **traits):
        super().__init__(**traits)
        self.signal_emitter = MessageListenerSignalEmitter()
        self.traits_init()

    def listener_actor_routine(self, message, topic):
        try:
            if topic == DEVICE_VIEWER_STATE_CHANGED:
                logger.info(f"Received device viewer message on topic: {topic}, message: {message}")
                self.signal_emitter.device_viewer_message_received.emit(message, topic)
                
            elif topic in [CHIP_INSERTED, DROPBOT_CONNECTED]:
                logger.info(f"Received dropbot connected signal: {topic}")
                self.signal_emitter.dropbot_connection_changed.emit(True)
                
            elif topic == DROPBOT_DISCONNECTED:
                logger.info(f"Received dropbot disconnected signal: {topic}")
                self.signal_emitter.dropbot_connection_changed.emit(False)

            elif topic == DROPLETS_DETECTED:
                logger.info(f"Received droplets detected response: {topic}")
                self.signal_emitter.droplets_detected.emit(message)

            elif topic == CALIBRATION_DATA:
                logger.info(f"Received calibration data, passing for now")
                self.signal_emitter.calibration_data_received.emit(message, topic)
                # pass

            elif topic == CAPACITANCE_UPDATED:
                logger.debug("Received capacitance updated message")
                self.signal_emitter.capacitance_updated.emit(message)
                
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
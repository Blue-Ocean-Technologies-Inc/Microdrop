import dramatiq

from traits.api import HasTraits, provides, Str, Instance

from PySide6.QtCore import Signal, QObject

from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor
from protocol_grid.state.messages import DeviceViewerMessageModel
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

class DeviceViewerListenerSignalEmitter(QObject):
    device_viewer_message_received = Signal(str, str)

class DeviceViewerListenerController(HasTraits):
    """
    Listens for device_viewer state change messages and emits a Qt signal.
    """
    signal_emitter = Instance(DeviceViewerListenerSignalEmitter)

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    listener_name = Str("protocol_grid_listener")

    def __init__(self, **traits):
        super().__init__(**traits)
        self.signal_emitter = DeviceViewerListenerSignalEmitter()
        self.traits_init()

    def listener_actor_routine(self, message, topic):
        logger.info(f"PROTOCOL_GRID: Received device_viewer message: {message} on topic: {topic}")
        # Qt signal for UI thread
        self.signal_emitter.device_viewer_message_received.emit(message, topic)

    def traits_init(self):
        logger.info("Starting DeviceViewer listener for protocol_grid")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine
        )
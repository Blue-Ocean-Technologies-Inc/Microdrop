from .dramatiq_pub_sub_helpers import publish_message
from dropbot.proxy import SerialProxy
from dropbot_controller.consts import DROPBOT_CONNECTED, DROPBOT_DISCONNECTED
import base_node_rpc as bnr
import functools as ft

from logger.logger_service import get_logger
logger = get_logger(__name__)

connection_flags = {"connected": DROPBOT_CONNECTED, "disconnected": DROPBOT_DISCONNECTED}


class DramatiqDropbotSerialProxy(SerialProxy):

    def connect(self):
        # If the monitor is already running, terminate it
        if self.monitor is not None:
            self.terminate()
            self.monitor = None

        # We need to signal to the dramatiq pub sub system that the dropbot has been 
        # disconnected/connected. We are writing a wrapper that will still do everything 
        # the original monitor function does except for the dramatiq pub sub publishing 
        # of the message this wrapper takes care of.

        _connection_state = { 'connected': False }

        # define the dramatiq pub sub wrappers
        def connection_event_wrapper(f, is_connected, *args, **kwargs):
            f(*args, **kwargs)

            # are we already in the state you're about to report?
            if _connection_state['connected'] == is_connected:
                return    # no diff, skip

            _connection_state['connected'] = is_connected

            pub_topic = DROPBOT_CONNECTED if is_connected else DROPBOT_DISCONNECTED
            publish_message("", pub_topic)

        self.monitor = bnr.ser_async.BaseNodeSerialMonitor(port=self.port)

        self.monitor.connected_event.set = ft.partial(connection_event_wrapper,
                                                      self.monitor.connected_event.set,
                                                      True)
        self.monitor.disconnected_event.set = ft.partial(connection_event_wrapper,
                                                         self.monitor.disconnected_event.set,
                                                         False)

        self.monitor.start()

        self.monitor.connected_event.wait()
        return self.monitor

from .dramatiq_pub_sub_helpers import publish_message
from dropbot.proxy import SerialProxy
from dropbot_controller.consts import DROPBOT_CONNECTED, DROPBOT_DISCONNECTED, CHIP_INSERTED, CHIP_CHECK
import base_node_rpc as bnr
import functools as ft

from microdrop_utils._logger import get_logger
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
        def connected_wrapper(f, *args, **kwargs):
            f(*args, **kwargs)
            
            # are we already in the state you're about to report?
            if _connection_state['connected']:
                return    # already connected, skip
            _connection_state['connected'] = True
            publish_message(f'dropbot_connected', DROPBOT_CONNECTED)
            # publish_message('', CHIP_CHECK) # this should be done at the handler for the dropbot connected.

        def disconnected_wrapper(f, *args, **kwargs):
            f(*args, **kwargs)
            
            # are we already in the state you're about to report?
            if not _connection_state['connected']:
                return    # already disconnected, skip
            _connection_state['connected'] = False
            publish_message(f'dropbot_disconnected', DROPBOT_DISCONNECTED)
            publish_message('False', CHIP_INSERTED)
        
        self.monitor = bnr.ser_async.BaseNodeSerialMonitor(port=self.port)

        self.monitor.connected_event.set = ft.partial(connected_wrapper,
                                                 self.monitor.connected_event.set)
        self.monitor.disconnected_event.set = ft.partial(disconnected_wrapper,
                                                    self.monitor.disconnected_event.set)

        self.monitor.start()

        self.monitor.connected_event.wait()
        return self.monitor

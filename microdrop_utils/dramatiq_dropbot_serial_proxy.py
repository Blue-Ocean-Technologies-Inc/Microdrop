from .dramatiq_pub_sub_helpers import publish_message
from dropbot.proxy import SerialProxy
import base_node_rpc as bnr
import functools as ft

CONNECTED = "dropbot/signals/connected"
DISCONNECTED = "dropbot/signals/disconnected"

connection_flags = {"connected": CONNECTED, "disconnected": DISCONNECTED}


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
        def publish_wrapper(f, signal_name, *args, **kwargs):
            f(*args, **kwargs)
            
            # are we already in the state you're about to report?
            if signal_name == 'connected':
                if _connection_state['connected']:
                    return    # already connected, skip
                _connection_state['connected'] = True
            else:  # 'disconnected'
                if not _connection_state['connected']:
                    return    # already disconnected, skip
                _connection_state['connected'] = False
            publish_message(f'dropbot_{signal_name}', connection_flags[signal_name])

        monitor = bnr.ser_async.BaseNodeSerialMonitor(port=self.port)

        monitor.connected_event.set = ft.partial(publish_wrapper,
                                                 monitor.connected_event.set,
                                                 'connected')
        monitor.disconnected_event.set = ft.partial(publish_wrapper, 
                                                    monitor.disconnected_event.set, 
                                                    'disconnected')

        monitor.start()

        monitor.connected_event.wait()
        self.monitor = monitor
        return self.monitor

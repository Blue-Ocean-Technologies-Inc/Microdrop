import sys
import os
import time

import mr_box_peripheral_board
import functools as ft

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# import base_node_rpc as bnr
from traits.api import HasTraits, Str, Callable, List, Union
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message, MessageRouterActor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
import dramatiq
from logger.logger_service import get_logger

logger = get_logger(__name__)

from microdrop_utils.hardware_device_monitoring_helpers import check_devices_available

magnetic_state_hwids = ['VID:PID=0403:6015']

class PeripheralDeviceConnectionMonitor(HasTraits):
    check_devices_available_actor = Callable
    port = Union(Str, None)
    hwids_to_check = List(Str())

    def _hwids_to_check_default(self):
        return magnetic_state_hwids

    def _check_devices_available_actor_default(self):

        @dramatiq.actor
        def check_devices_available_actor():
            """
            Method to find the USB port of the device with hwid in hwids_to_check if it is connected.
            """
            try:
                port = check_devices_available(magnetic_state_hwids)

                if port is None:
                    # reset the port names list to capture a reconnection in the same port.
                    self.port = None
                    publish_message('No device available for connection', 'peripheral/error')

                # Check if there are new port names
                elif port != self.port:
                    self.port = port
                    publish_message(f'New device found on port: {port}', 'peripheral/info')

                    # publish the new port name
                    publish_message(port, 'peripheral/port')

                else:
                    # publish_message("No New device found", 'peripheral/info')
                    logger.debug('No new device found')

            except Exception as e:
                # reset the port names list to capture reconnection in the same port.
                self.port = None
                publish_message(f'No device available for connection with exception {e}', 'peripheral/error')

        return check_devices_available_actor


@dramatiq.actor
def print_message(message=str, topic=str, *args, **kwargs):
    print(f"PRINT_MESSAGE_SERVICE: Received message: {message}! from topic: {topic}")



### Manager proxy connection #########
def disconnected_wrapper(f, *args, **kwargs):
    f(*args, **kwargs)
    publish_message(f'device disconnected', 'peripheral/disconnected')

proxy = None

@dramatiq.actor
def serial_proxy_manager(port_name:Str, topic: Str, *args, **kwargs):
    global proxy

    if topic == "peripheral/disconnected":
        if proxy is not None:
            proxy.terminate()
            proxy = None
        return

    try:
        proxy = mr_box_peripheral_board.SerialProxy(port=port_name)
        proxy.monitor.disconnected_event.set = ft.partial(disconnected_wrapper, proxy.monitor.disconnected_event)
        time.sleep(2)
        print(proxy.ram_free())

    except Exception as e:
        logger.error(f'Serial proxy error: {e}')
        publish_message('No device available for connection', 'peripheral/error')

##########################################

def main(args):
    message_router_actor = MessageRouterActor()

    message_router_actor.message_router_data.add_subscriber_to_topic('peripheral/#', 'print_message')
    message_router_actor.message_router_data.add_subscriber_to_topic('peripheral/port', 'serial_proxy_manager')
    message_router_actor.message_router_data.add_subscriber_to_topic('peripheral/disconnected', 'serial_proxy_manager')

    example_instance = PeripheralDeviceConnectionMonitor()
    scheduler = BlockingScheduler()
    scheduler.add_job(
        example_instance.check_devices_available_actor.send,
        IntervalTrigger(seconds=1),
    )
    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()

    return 0


if __name__ == "__main__":

    import sys
    import os

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from microdrop_utils.broker_server_helpers import dramatiq_workers_context, redis_server_context

    with redis_server_context(), dramatiq_workers_context():
            main(sys.argv)

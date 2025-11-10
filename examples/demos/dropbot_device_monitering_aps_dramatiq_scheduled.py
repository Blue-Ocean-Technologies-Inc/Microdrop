import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# import base_node_rpc as bnr
from traits.api import HasTraits, Str, Callable, List
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message, MessageRouterActor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
import dramatiq
from serial.tools.list_ports import grep, comports
from logger.logger_service import get_logger
import re

logger = get_logger(__name__)


def check_connected_ports_hwid(hwid = 'USB VID:PID=16C0:0483'):#id_to_screen, regexp='USB Serial'):
    """
    Check connected USB ports for a specific hardware id.
    """

    # get connected ports to usb serial
    connected_ports = comports()#grep(regexp)

    # initialize list to store valid ports
    valid_ports = []

    # go through connected ports and check if the hardware id matches the id
    # try using regex: neglect PID use the VID
    for port in connected_ports:
        # Regex pattern to find the VID in the hwid string
        # pattern = re.compile(f".*{id_to_screen}.*")

        # Search for the pattern in the string
        # teensy = re.search(pattern, port.hwid)

        # if bool(teensy):
        if hwid in port.hwid:
            valid_ports.append(port)

    return valid_ports


class DropBotDeviceConnectionMonitor(HasTraits):
    check_dropbot_devices_available_actor = Callable
    port_names = List(Str())
    hwids_to_check = List(Str())

    def _hwids_to_check_default(self):
        return ["VID:PID=16C0:"]

    def _check_dropbot_devices_available_actor_default(self):
        return self.create_check_dropbot_devices_available_actor()

    def create_check_dropbot_devices_available_actor(self):
        @dramatiq.actor
        def check_dropbot_devices_available_actor():
            """
            Method to find the USB port of the DropBot if it is connected.
            """
            try:
                # Iterate through the hardware IDs to check
                for hwid in self.hwids_to_check:

                    # Find the valid ports for the hardware ID
                    valid_ports = check_connected_ports_hwid(hwid)

                    # Check if there are valid ports
                    if valid_ports:

                        # Extract port names
                        port_names = [port.device for port in valid_ports]

                        # Check if there are new port names
                        if port_names != self.port_names:
                            new_ports = [port_name for port_name in port_names if port_name not in self.port_names]

                            if new_ports:
                                self.port_names.extend(new_ports)

                                # Publish information about the new ports
                                for port_name in new_ports:
                                    publish_message(f'New DropBot found on port: {port_name}', 'dropbot/info')

                                # publish the first port name on the list
                                publish_message(port_names[0], 'dropbot/port')

                        else:
                            # publish_message("No New DropBot found", 'dropbot/info')
                            logger.debug('No new Dropbot found')
                    else:
                        # reset the port names list to capture a reconnection in the same port.
                        self.port_names = []
                        publish_message('No DropBot available for connection', 'dropbot/error')

            except Exception as e:
                # reset the port names list to capture reconnection in the same port.
                self.port_names = []
                publish_message(f'No DropBot available for connection with exception {e}', 'dropbot/error')

            # this is the other method. It can work with all ids as long as it is a dropbot.
            # so it avoids the need to know the id of the dropbot. But it needs to setup a conenction with the dropbot first.
            # This might be intensive of a task to do every second.

            # try:
            #
            #     # Find DropBots
            #     df_devices = bnr.available_devices(timeout=.5)
            #
            #     if not df_devices.shape[0]:
            #         self.port = ''
            #         raise IOError('No DropBot available for connection')
            #
            #     df_dropbots = df_devices.loc[df_devices.device_name.isin(['dropbot', b'dropbot'])]
            #
            #     if not df_dropbots.shape[0]:
            #         self.port = ''
            #         raise IOError('No DropBot available for connection')
            #
            #     port = df_dropbots.index[0]
            #
            #     if port != self.port:
            #         self.port = port
            #         publish_message(f'New dropbot found on port {port}', 'dropbot/port')
            #
            # except Exception as e:
            #     # print(f'Error: {e}')
            #     publish_message(str(e), 'dropbot/error')

        return check_dropbot_devices_available_actor


@dramatiq.actor
def print_dropbot_message(message=str, topic=str, timestamp=None):
    print(f"PRINT_DROPBOT_MESSAGE_SERVICE: Received message: {message}! from topic: {topic}")


@dramatiq.actor
def make_serial_proxy(port_name:Str, topic: Str, timestamp=None):
    import dropbot
    try:
        proxy = dropbot.SerialProxy(port=port_name)
        print(proxy.ram_free())
    except (IOError, AttributeError):
        publish_message('No DropBot available for connection', 'dropbot/error')
    except dropbot.proxy.NoPower:
        publish_message('No power to DropBot', 'dropbot/error/NoPower')


def main(args):
    message_router_actor = MessageRouterActor()

    message_router_actor.message_router_data.add_subscriber_to_topic('dropbot/#', 'print_dropbot_message')
    message_router_actor.message_router_data.add_subscriber_to_topic('dropbot/port', 'make_serial_proxy')

    example_instance = DropBotDeviceConnectionMonitor()
    scheduler = BlockingScheduler()
    scheduler.add_job(
        example_instance.check_dropbot_devices_available_actor.send,
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

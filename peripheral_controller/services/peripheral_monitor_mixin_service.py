import json

import dropbot
from traits.api import provides, HasTraits, Bool, Instance, Str
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.base import STATE_STOPPED, STATE_RUNNING, STATE_PAUSED

from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.dramatiq_peripheral_serial_proxy import DramatiqPeripheralSerialProxy
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from microdrop_utils.hardware_device_monitoring_helpers import check_devices_available
from ..interfaces.i_peripheral_control_mixin_service import IPeripheralControlMixinService

from ..consts import MR_BOX_HWID, DEVICE_NAME, CONNECTED

logger = get_logger(__name__)

# silence all APScheduler job-exception logs
get_logger('apscheduler.executors.default').setLevel(level="WARNING")


@provides(IPeripheralControlMixinService)
class PeripheralMonitorMixinService(HasTraits):
    """
    A mixin Class that adds methods to monitor a dropbot connection and get some dropbot information.
    """
    id = Str(f"{DEVICE_NAME}_monitor_mixin_service")
    name = Str(f'{DEVICE_NAME.title()} Monitor Mixin')
    monitor_scheduler = Instance(BackgroundScheduler,
                                 desc="An AP scheduler job to periodically look for connected ports."
                                 )

    _error_shown = Bool(False)  # Track if we've shown the error for current disconnection

    ######################################## Methods to Expose #############################################

    def on_start_device_monitoring_request(self, timestamped_message: 'TimestampedMessage'):
        """
        Method to start looking for devices connected using their hwids.
        If device already connected, publishes device connected signal.

        message should be a json serialized list of hwids to check.
        """

        if timestamped_message.content:
            hwids_to_check = json.loads(timestamped_message.content)
        else:
            hwids_to_check = [MR_BOX_HWID]

        # if device already connected, exit after publishing connection and chip details
        if self.connection_active:
            publish_message(f'{self._device_name}_connected', CONNECTED)
            return None

        ## handle cases where monitor scheduler object already exists
        if hasattr(self, "monitor_scheduler"):
            if isinstance(self.monitor_scheduler, BackgroundScheduler):

                if self.monitor_scheduler.state == STATE_RUNNING:
                    logger.warning(f"{self._device_name} connections are already being monitored.")

                elif self.monitor_scheduler.state == STATE_STOPPED:
                    self.monitor_scheduler.start()
                    logger.info(f"{self._device_name} connection monitoring started now.")

                elif self.monitor_scheduler.state == STATE_PAUSED:
                    self.monitor_scheduler.resume()
                    logger.info(f"{self._device_name} connection monitoring was paused, now it is resumed.")

                else:
                    logger.error(f"Invalid {self._device_name} monitor scheduler state: it is {self.monitor_scheduler.state}")

                return None

        ## monitor was never created, so we can make one now:
        def check_devices_with_error_handling():
            """
            Wrapper to handle errors from check_devices_available.
            """
            try:
                return check_devices_available(hwids_to_check)
            except Exception as e:
                if not self._error_shown:
                    logger.error(f"{str(e)}")
                    self._error_shown = True
                return None
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=check_devices_with_error_handling,
            trigger=IntervalTrigger(seconds=2),
        )
        scheduler.add_listener(self._on_port_found, EVENT_JOB_EXECUTED)
        self.monitor_scheduler = scheduler

        logger.info(f"{self._device_name} monitor created and started")
        # self._error_shown = False  # Reset error state when starting monitoring
        self.monitor_scheduler.start()

    def on_retry_connection_request(self, message):
        if self.connection_active:
            logger.info(f"Retry connection request rejected: {self._device_name} already connected")
            return
        logger.info(f"Attempting to retry connecting with a {self._device_name}")
        self.monitor_scheduler.resume()

    ############################################################
    # Connect / Disconnect signal handlers
    ############################################################

    def on_disconnected_signal(self, message):
        # set connection inactive in case it was not changed.
        if self.connection_active:
            self.connection_active = False

        # Terminate the proxy monitor and reset it to None to allow new connection to set the monitor.
        if self.proxy is not None:
            if self.proxy.monitor is not None:
                self.proxy.terminate()
                logger.info(f" {self._device_name} Proxy terminated")
                self.proxy.monitor = None
                logger.info(f"Sending Signal to Resumed {self._device_name} monitor")

        logger.info(f" {self._device_name} disconnected. Resuming search for {self._device_name} connection.")
        self.on_retry_connection_request(message="")

    def on_connected_signal(self, message):
        # set connection active in case it was not changed.
        if not self.connection_active:
            self.connection_active = True

    ################################# Protected methods ######################################
    def _on_port_found(self, event):
        """
        Method defining what to do when device has been found on a port.
        """
        # if check_devices returned nothing => still disconnected
        if not event.retval:
            return
        
        logger.debug(f"{self._device_name} port found")
        self.monitor_scheduler.pause()
        logger.debug(f"Paused {self._device_name} monitor")
        self.port_name = str(event.retval)
        logger.info(f'Attempting to connect to {self._device_name} on port: %s', self.port_name)
        self._connect_to_device(port_name=self.port_name)
        self._error_shown = False  # Reset error state when device is found

    def _connect_to_device(self, port_name):
        """
        Once a port is found, attempt to connect to the Device on that port.

        IF already connected, do nothing.
        IF not connected, attempt to connect to the Device on the port.

        FAIL IF:
        - No Device available for connection - USB not connected
        """
        if self.proxy is None or getattr(self, 'proxy.monitor', None) is None:

            logger.debug(f"{self._device_name} not connected. Attempting to connect")

            ############################### Attempt to make a proxy object #############################

            try:
                logger.debug(f"Attempting to create {self._device_name} serial proxy on port {port_name}")
                self.proxy = DramatiqPeripheralSerialProxy(port=port_name)
                logger.info(f"{self._device_name} connected on port {port_name}")

                # once setup, run on connected routine in case it did not get triggered
                if not self.connection_active:
                    self.on_connected_signal("")

            except Exception as e:
                # This is for any other unexpected error during the connection process.
                logger.error(f"An unexpected error occurred with {self._device_name}: {e}", exc_info=True)

            ###########################################################################################

            finally:
                # If the connection is not active, it means the 'try' block failed or
                # was never successfully completed: run disconnect routine.
                if not self.connection_active:
                    self.on_disconnected_signal("")

        # if the device is already connected
        else:
            logger.info(f"{self._device_name.title()} already connected on port {port_name}")

import json

from traits.api import provides, HasTraits, Bool, Instance, Str, List
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.base import STATE_STOPPED, STATE_RUNNING, STATE_PAUSED

from microdrop_utils.datetime_helpers import TimestampedMessage
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.hardware_device_monitoring_helpers import check_devices_available
from logger.logger_service import get_logger

from ..interfaces.i_peripheral_device_control_mixin_service import IPeripheralDeviceControlMixinService

logger = get_logger(__name__)

# silence all APScheduler job-exception logs
get_logger('apscheduler.executors.default').setLevel(level="WARNING")


@provides(IPeripheralDeviceControlMixinService)
class PeripheralDeviceMonitorMixinService(HasTraits):
    """Generic mixin that monitors for a serial peripheral by HWID, connects to
    it when found, and maintains/resumes that connection.

    Subclasses customize the device by overriding:
        ``_default_hwids`` — HWIDs to scan for when no payload is supplied.
        ``_make_proxy(port_name)`` — build and return the device's serial proxy.
        ``_find_port(hwids)`` — locate the serial port (defaults to a USB-serial
            HWID grep); override when the device's port description differs.
    """
    id = Str("peripheral_device_monitor_mixin_service")
    name = Str("Peripheral Device Monitor Mixin")
    monitor_scheduler = Instance(
        BackgroundScheduler,
        desc="An AP scheduler job to periodically look for connected ports.")

    _default_hwids = List(Str)
    _error_shown = Bool(False)  # Track if we've shown the error for current disconnection
    _searching = Bool(False)    # Is the monitor thread actively scanning right now?

    def _set_searching(self, active, force=False):
        """Publish the connection-search state so a frontend can, e.g., disable its
        'search connection' control while a scan is already running. Publishes only
        on change unless ``force`` (used when answering an explicit start request,
        so a late-subscribing frontend learns the current state)."""
        if force or self._searching != active:
            self._searching = active
            publish_message(message=json.dumps(active), topic=self.searching_topic)
            logger.info(f"{self._device_name} searching: {active}")

    # ---- device-specific hooks (override in subclasses) ---------------------

    def _make_proxy(self, port_name):
        """Build and return the device serial proxy connected on ``port_name``."""
        raise NotImplementedError

    def _find_port(self, hwids):
        """Return the serial port for a device matching one of ``hwids``."""
        return check_devices_available(hwids)

    ######################################## Methods to Expose #############################################

    def on_start_device_monitoring_request(self, timestamped_message: 'TimestampedMessage'):
        """Start looking for devices connected using their hwids. If the device is
        already connected, publishes the connected signal. The message may be a
        JSON-serialized list of hwids to check; otherwise ``_default_hwids`` is used.
        """
        if timestamped_message.content:
            hwids_to_check = json.loads(timestamped_message.content)
        else:
            hwids_to_check = list(self._default_hwids)

        # if device already connected, exit after publishing connection
        if self.connection_active:
            publish_message(f'{self._device_name}_connected', self.connected_topic)
            self._set_searching(False, force=True)
            return None

        ## handle cases where monitor scheduler object already exists
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
                logger.error(
                    f"Invalid {self._device_name} monitor scheduler state: it is {self.monitor_scheduler.state}")
            self._set_searching(True, force=True)
            return None

        ## monitor was never created, so we can make one now:
        def check_devices_with_error_handling():
            """Wrapper to handle errors from the port finder."""
            try:
                return self._find_port(hwids_to_check)
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
        self.monitor_scheduler.start()
        self._set_searching(True, force=True)

    def on_retry_connection_request(self, message):
        if self.connection_active:
            logger.info(f"Retry connection request rejected: {self._device_name} already connected")
            return
        logger.info(f"Attempting to retry connecting with a {self._device_name}")
        self.monitor_scheduler.resume()
        self._set_searching(True)

    ############################################################
    # Connect / Disconnect signal handlers
    ############################################################

    def on_disconnected_signal(self, message):
        # set connection inactive in case it was not changed.
        if self.connection_active:
            self.connection_active = False

        # Terminate the proxy and reset it to None to allow a new connection.
        if self.proxy is not None:
            try:
                self.proxy.terminate()
                logger.info(f" {self._device_name} Proxy terminated")
            except Exception as e:
                logger.debug(f"Error terminating {self._device_name} proxy on disconnect: {e}")
            self.proxy = None

        logger.info(f" {self._device_name} disconnected. Resuming search for {self._device_name} connection.")
        self.on_retry_connection_request(message="")

    def on_connected_signal(self, message):
        # set connection active in case it was not changed.
        if not self.connection_active:
            self.connection_active = True
        # Connected → the scan is over (the monitor pauses on a found port).
        self._set_searching(False)

    ################################# Protected methods ######################################
    def _on_port_found(self, event):
        """What to do when the device has been found on a port."""
        # if the port finder returned nothing => still disconnected
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
        """Once a port is found, attempt to connect to the device on that port.
        If already connected, do nothing.
        """
        if self.proxy is None:
            logger.debug(f"{self._device_name} not connected. Attempting to connect")
            try:
                logger.debug(f"Attempting to create {self._device_name} serial proxy on port {port_name}")
                self.proxy = self._make_proxy(port_name)
                logger.info(f"{self._device_name} connected on port {port_name}")

                # once setup, run on connected routine in case it did not get triggered
                if not self.connection_active:
                    self.on_connected_signal("")

            except Exception as e:
                logger.error(f"An unexpected error occurred with {self._device_name}: {e}", exc_info=True)

            finally:
                # If the connection is not active, the 'try' block failed: run disconnect routine.
                if not self.connection_active:
                    self.on_disconnected_signal("")

        else:
            logger.info(f"{self._device_name.title()} already connected on port {port_name}")

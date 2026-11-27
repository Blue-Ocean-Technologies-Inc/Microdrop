# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import atexit
import functools
import time

# Third-party imports.
import dropbot
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED
from apscheduler.triggers.interval import IntervalTrigger

# Enthought library imports.
from traits.api import Bool, HasTraits, Instance, Str, observe, provides

# Microdrop package imports.
from notifications.consts import LOG_RECORDED_EXTRA

# Microdrop utils imports.
from microdrop_utils.dramatiq_dropbot_serial_proxy import DramatiqDropbotSerialProxy
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.hardware_device_monitoring_helpers import (
    DeviceNotFoundError,
    check_devices_available,
)

# Local imports.
from ..consts import (
    DROPBOT_CHIP_INSERTED_KEY,
    DROPBOT_CONNECTED,
    DROPBOT_DB3_120_HWID,
    DROPBOT_ERROR,
    DROPBOT_NO_POWER_KEY,
    NO_DROPBOT_AVAILABLE,
    NO_POWER,
    hardware_limits_updated_publisher,
)
from ..dropbot_controller_base import describe_proxy
from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from .dropbot_state_mirror import clear_dropbot_state, mirror_dropbot_state

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def wait_for_proxy(timeout=2, poll_interval=0.1):
    """Decorator that polls until self.proxy is live, with a timeout.

    A disconnect keeps the old proxy but clears its monitor, and the new
    proxy's constructor emits ``connected`` before it is assigned — so a
    non-None proxy alone may be the dead one from the last connection.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            def proxy_is_live():
                return self.proxy and getattr(self.proxy, "monitor", None)

            elapsed = 0
            logger.info(
                f"{func.__name__}: waiting for proxy {describe_proxy(self.proxy)}"
            )

            while not proxy_is_live() and elapsed < timeout:
                time.sleep(poll_interval)
                elapsed += poll_interval

            logger.info(
                f"{func.__name__}: waited {elapsed:.1f}s {describe_proxy(self.proxy)}"
            )

            if not proxy_is_live():
                logger.warning(f"Timed out waiting for proxy after {timeout}s")
                return None
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


# silence all APScheduler job-exception logs
get_logger("apscheduler.executors.default").setLevel(level="WARNING")


@provides(IDropbotControlMixinService)
class DropbotMonitorMixinService(HasTraits):
    """
    A mixin Class that adds methods to monitor a dropbot connection and get
    some dropbot information.
    """

    id = Str("dropbot_monitor_mixin_service")
    name = Str("Dropbot Monitor Mixin")
    monitor_scheduler = Instance(
        BackgroundScheduler,
        desc="An AP scheduler job to periodically look for dropbot connected ports.",
    )
    _error_shown = Bool(
        False
    )  # Track if we've shown the error for current disconnection
    _no_power = Bool(False)

    @observe("_no_power")
    def _mirror_no_power_to_app_globals(self, event):
        """Mirror the no-power flag to app_globals, as the connection state
        is: a reader the ``NO_POWER`` signal wakes sees it set."""
        mirror_dropbot_state({DROPBOT_NO_POWER_KEY: event.new})

    ############################ Methods to Expose #############################

    def on_start_device_monitoring_request(self, hwids_to_check):
        """
        Method to start looking for dropbots connected using their hwids.
        If dropbot already connected, publishes dropbot connected signal.
        """
        # if dropbot already connected, exit after publishing connection and
        # chip details
        if self.dropbot_connection_active:
            publish_message("dropbot_connected", DROPBOT_CONNECTED)
            self.on_chip_check_request("")  # from base class
            return None

        ## handle cases where monitor scheduler object already exists
        if hasattr(self, "monitor_scheduler"):
            if isinstance(self.monitor_scheduler, BackgroundScheduler):
                if self.monitor_scheduler.state == STATE_RUNNING:
                    logger.warning("Dropbot connections are already being monitored.")

                elif self.monitor_scheduler.state == STATE_STOPPED:
                    self.monitor_scheduler.start()
                    logger.info("Dropbot connection monitoring started now.")

                elif self.monitor_scheduler.state == STATE_PAUSED:
                    self.monitor_scheduler.resume()
                    logger.info(
                        "Dropbot connection monitoring was paused, now it is resumed."
                    )

                else:
                    logger.error(
                        f"Invalid dropbot monitor scheduler state: "
                        f"it is {self.monitor_scheduler.state}"
                    )

                return None

        ## monitor was never created, so we can make one now:

        if not hwids_to_check:
            hwids_to_check = [DROPBOT_DB3_120_HWID]

        def check_devices_with_error_handling():
            """
            Wrapper to handle errors from check_devices_available.
            """
            try:
                return check_devices_available(hwids_to_check)

            # No DropBot plugged in is the normal idle state; the search
            # repeats, so it is said once per search, and quietly.
            except DeviceNotFoundError as e:
                if not self._error_shown:
                    logger.info(f"{e}; still looking")
                    self._error_shown = True

                return None

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
        scheduler.add_listener(self._on_dropbot_port_found, EVENT_JOB_EXECUTED)
        self.monitor_scheduler = scheduler

        logger.info("DropBot monitor created and started")
        # self._error_shown = False  # Reset error state when starting monitoring
        self.monitor_scheduler.start()
        # Interpreter-exit backstop: atexit callbacks run before Python
        # kills executor pools, so the scheduler dies quietly even on an
        # exit path that never reaches plugin stop (a signal handler's
        # sys.exit, a killed window).
        atexit.register(self._shutdown_monitor_scheduler)

    def cleanup(self):
        """Stop the port scanner before the connection teardown: a
        BackgroundScheduler nothing shuts down outlives plugin stop,
        and once interpreter shutdown kills its executor pool every
        tick spams 'cannot schedule new futures after shutdown'."""
        self._shutdown_monitor_scheduler()
        super().cleanup()

        # A clean stop leaves no state for the next session to misread.
        clear_dropbot_state()

    def _shutdown_monitor_scheduler(self):
        """Idempotent scheduler shutdown, shared by cleanup and the
        atexit backstop."""
        scheduler = self.monitor_scheduler
        if (
            isinstance(scheduler, BackgroundScheduler)
            and scheduler.state != STATE_STOPPED
        ):
            try:
                scheduler.shutdown(wait=False)
                logger.info("DropBot monitor stopped.")
            except Exception as exc:
                logger.debug(f"Error stopping the DropBot monitor: {exc}")

    def on_retry_connection_request(self, message):
        if self.dropbot_connection_active:
            logger.info("Retry connection request rejected: Dropbot already connected")
            return
        logger.info("Attempting to retry connecting with a dropbot")
        self.monitor_scheduler.resume()

    ############################################################
    # Connect / Disconnect signal handlers
    ############################################################

    def on_disconnected_signal(self, message):
        # set connection inactive in case it was not changed.
        if self.dropbot_connection_active:
            self.dropbot_connection_active = False

        self.realtime_mode = False

        # Terminate the proxy monitor and reset it to None to allow new
        # connection to set the monitor.
        logger.info(f"Disconnected signal {describe_proxy(self.proxy)}")

        if self.proxy is not None:
            if self.proxy.monitor is not None:
                self.proxy.terminate()
                logger.info("Proxy terminated")
                self.proxy.monitor = None
                logger.info("Sending Signal to Resumed DropBot monitor")

        # if there is no power, we wait for user to send retry connection
        # request; else: we automatically do it
        if self._no_power:
            logger.info(
                "There was no power detected before the disconnection. "
                "Request retry after supplying power."
            )

        else:
            logger.info("DropBot disconnected. Resuming search for dropbot connection.")
            self.on_retry_connection_request(message="")

    @wait_for_proxy(timeout=4)
    def on_connected_signal(self, message):
        # set connection active in case it was not changed.
        if self._no_power:
            logger.warning("There was no power detected, on connected routine ignored.")
            return
        if not self.dropbot_connection_active:
            logger.info("Dropbot Connected")
            self.dropbot_connection_active = True

        # Expose hardware limits as readonly info on the preferences model
        logger.info(f"Reading hardware limits {describe_proxy(self.proxy)}")

        try:
            with self.proxy.transaction_lock:
                self.preferences._hardware_max_voltage = self.proxy.config.max_voltage
                self.preferences._hardware_max_frequency = (
                    self.proxy.config.max_frequency
                )

            cap_interval = self.proxy.state["capacitance_update_interval_ms"]
            logger.info(
                f"DropBot hardware report: \n"
                f"Max Voltage: {self.preferences._hardware_max_voltage} V\n"
                f"Max Frequency: {self.preferences._hardware_max_frequency} Hz\n"
                f"Capacitance Update Interval (ms): {cap_interval}\n"
            )

        except Exception as e:
            logger.warning(f"Could not read hardware limits from proxy config: {e}")

            return

        # The preferences' observer has written the maxima to app_globals.
        hardware_limits_updated_publisher.publish(
            {
                "max_voltage": self.preferences._hardware_max_voltage,
                "max_frequency": self.preferences._hardware_max_frequency,
            }
        )

    ############################ Protected methods #############################
    def _on_dropbot_port_found(self, event):
        """
        Method defining what to do when dropbot has been found on a port.
        """
        # if check_devices returned nothing => still disconnected
        if not event.retval:
            return

        self.monitor_scheduler.pause()
        logger.debug("DropBot port found; Paused DropBot monitor")

        self.port_name = str(event.retval)
        self._attempt_dropbot_port_connection(port_name=self.port_name)
        self._error_shown = False  # Reset error state when device is found

    def _attempt_dropbot_port_connection(self, port_name):
        """
        Once a port is found, attempt to connect to the DropBot on that port.

        IF already connected, do nothing.
        IF not connected, attempt to connect to the DropBot on the port.

        FAIL IF:
        - No DropBot available for connection - USB not connected
        - No power to DropBot - power supply not connected
        """
        self._no_power = False  # Reset no power state when device is found

        # A chip read on a previous connection is stale until this one's
        # setup reads it again.
        mirror_dropbot_state({DROPBOT_CHIP_INSERTED_KEY: None})

        if self.proxy is None or getattr(self.proxy, "monitor", None) is None:
            ################# Attempt to make a proxy object ##################

            logger.info(
                f"Attempting to create DropBot serial proxy on port {port_name}"
            )

            try:
                logger.info(f"Replacing proxy {describe_proxy(self.proxy)}")
                self.proxy = DramatiqDropbotSerialProxy(port=port_name)
                logger.info(
                    f"DropBot connected on port {port_name} "
                    f"{describe_proxy(self.proxy)}"
                )

                # this will send out a connected signal to the message router
                # if successful
                # triggering the self.on_connected_signal method immediately.
                self._on_dropbot_proxy_connected()

                # once dropbot setup, run on connected routine in case it did
                # not get triggered
                if not self.dropbot_connection_active:
                    self.on_connected_signal("")

            except (IOError, AttributeError) as e:
                logger.error(
                    f"IO or Attribute Error connecting to DropBot: {e}", exc_info=True
                )
                publish_message(topic=NO_DROPBOT_AVAILABLE, message=str(e))

            except dropbot.proxy.NoPower as e:
                # The no-power dialog lists it in the notifications drawer.
                logger.critical(
                    "DropBot has no power.", exc_info=True, extra=LOG_RECORDED_EXTRA
                )
                # Set (and so mirrored) before the signal a reader wakes on.
                self._no_power = True
                publish_message(topic=NO_POWER, message=str(e))

            except Exception as e:
                # This is for any other unexpected error during the connection process.
                logger.error(
                    f"An unexpected error occurred with DropBot: {e}", exc_info=True
                )
                publish_message(topic=DROPBOT_ERROR, message=str(e))

            ###########################################################################################

            finally:
                # If the connection is not active, it means the 'try' block failed or
                # was never successfully completed: run disconnect routine.
                if not self.dropbot_connection_active:
                    self.on_disconnected_signal("")

        # if the dropbot is already connected
        else:
            logger.info(f"Dropbot already connected on port {port_name}")

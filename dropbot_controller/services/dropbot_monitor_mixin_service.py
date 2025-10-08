import functools
import json
import traceback

import dropbot
from dropbot import EVENT_CHANNELS_UPDATED, EVENT_SHORTS_DETECTED, EVENT_ENABLE
from traits.api import provides, HasTraits, Bool, Instance, Str
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_dropbot_serial_proxy import DramatiqDropbotSerialProxy, connection_flags
from microdrop_utils.hardware_device_monitoring_helpers import check_devices_available
from ..interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

from ..consts import NO_DROPBOT_AVAILABLE, SHORTS_DETECTED, NO_POWER, DROPBOT_DB3_120_HWID, RETRY_CONNECTION, \
    OUTPUT_ENABLE_PIN, CHIP_INSERTED, DROPBOT_CONNECTED, DROPBOT_ERROR, DROPBOT_DISCONNECTED

logger = get_logger(__name__, level="DEBUG")

# silence all APScheduler job-exception logs
get_logger('apscheduler.executors.default').setLevel(level="WARNING")

@provides(IDropbotControlMixinService)
class DropbotMonitorMixinService(HasTraits):
    """
    A mixin Class that adds methods to monitor a dropbot connection and get some dropbot information.
    """

    id = Str("dropbot_monitor_mixin_service")
    name = Str('Dropbot Monitor Mixin')
    monitor_scheduler = Instance(BackgroundScheduler,
                                 desc="An AP scheduler job to periodically look for dropbot connected ports."
                                 )
    _error_shown = Bool(False)  # Track if we've shown the error for current disconnection
    _no_power = Bool(False) 


    ######################################## Methods to Expose #############################################
    def on_start_device_monitoring_request(self, hwids_to_check):
        """
        Method to start looking for dropbots connected using their hwids.
        If dropbot already connected, publishes dropbot connected signal.
        """
        if self.dropbot_connection_active:
            self.on_chip_check_request("")
            return

        if not hwids_to_check:
            hwids_to_check = [DROPBOT_DB3_120_HWID]

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
        scheduler.add_listener(self._on_dropbot_port_found, EVENT_JOB_EXECUTED)
        self.monitor_scheduler = scheduler

        logger.info("DropBot monitor created and started")
        # self._error_shown = False  # Reset error state when starting monitoring
        self.monitor_scheduler.start()

    def on_detect_shorts_request(self, message):
        if self.proxy is not None:
            shorts_list = self.proxy.detect_shorts()
            shorts_dict = {'Shorts_detected': shorts_list}
            logger.info(f"Detected shorts: {shorts_dict}")
            publish_message(topic=SHORTS_DETECTED, message=json.dumps(shorts_dict))

    @debounce(wait_seconds=1) # take into account rapid chip insertion changes
    def on_chip_check_request(self, message):
        if self.proxy is not None:
            chip_check_result = not bool(self.proxy.digital_read(OUTPUT_ENABLE_PIN))
            logger.info(f"Chip check result: {chip_check_result}")
            publish_message(topic=CHIP_INSERTED, message=f'{chip_check_result}')
    
    def on_retry_connection_request(self, message):
        if self.dropbot_connection_active:
            logger.info(f"Retry connection request rejected: Dropbot already connected")
            return
        logger.info("Attempting to retry connecting with a dropbot")
        self.monitor_scheduler.resume()

    def on_halt_request(self, message):
        self.proxy.turn_off_all_channels()
        self.proxy.update_state(hv_output_selected=False,
                                hv_output_enabled=False,
                                voltage=0)
        logger.error("Halted DropBot: Disconnect everything and reconnect")
    
    ############################################################
    # Connect / Disconnect signal handlers
    ############################################################

    def on_disconnected_signal(self, message):
        self.dropbot_connection_active = False
        if not self._no_power:
            logger.info(
                "DropBot disconnected. Attempting to terminate proxy and resume monitoring to find DropBot again.")

            if self.proxy is not None:
                if self.proxy.monitor is not None:
                    self.proxy.terminate()
                    logger.info("Proxy terminated")
                    self.proxy.monitor = None
                    self.monitor_scheduler.resume()
                    logger.info("Sending Signal to Resumed DropBot monitor")
                    self.on_retry_connection_request(message="")

    def on_connected_signal(self, message):
        # Conduct a chip check
        self.dropbot_connection_active = True
        self.on_chip_check_request("")

    ################################# Protected methods ######################################
    def _on_dropbot_port_found(self, event):
        """
        Method defining what to do when dropbot has been found on a port.
        """
        # if check_devices returned nothing => still disconnected
        if not event.retval:
            return
        
        logger.debug("DropBot port found")
        self.monitor_scheduler.pause()
        logger.debug("Paused DropBot monitor")
        self.port_name = str(event.retval)
        logger.info('Attempting to connect to DropBot on port: %s', self.port_name)
        self._no_power = False # Reset no power state when device is found
        self._connect_to_dropbot(port_name=self.port_name)
        self._error_shown = False  # Reset error state when device is found

    def _connect_to_dropbot(self, port_name):
        """
        Once a port is found, attempt to connect to the DropBot on that port.

        IF already connected, do nothing.
        IF not connected, attempt to connect to the DropBot on the port.

        FAIL IF:
        - No DropBot available for connection - USB not connected
        - No power to DropBot - power supply not connected
        """
        self._no_power = False
        err = None

        if self.proxy is None or getattr(self, 'proxy.monitor', None) is None:

            logger.debug("Dropbot not connected. Attempting to connect")

            ############################### Attempt to make a proxy object #############################

            try:
                logger.debug(f"Attempting to create DropBot serial proxy on port {port_name}")
                self.proxy = DramatiqDropbotSerialProxy(port=port_name)
                # this will send out a connected signal to the message router if successful
                logger.info(f"DropBot connected on port {port_name}")

                self._on_dropbot_proxy_connected()

                # once dropbot setup, set connection to active
                self.dropbot_connection_active = True

                # self.on_chip_check_request("")
                
            except (IOError, AttributeError) as e:
                publish_message(topic=NO_DROPBOT_AVAILABLE, message=str(e))
                err = f'{traceback.format_exc()}'
                if self.proxy is not None:
                    self.proxy.terminate()

            except dropbot.proxy.NoPower as e:
                logger.critical("DropBot has no power.")
                self._no_power = True
                publish_message(topic=NO_POWER, message=str(e))
                err = f'{traceback.format_exc()}'
                if self.proxy is not None:
                    self.proxy.terminate()

            except Exception as e:
                err = f'{traceback.format_exc()}'
                publish_message(topic=DROPBOT_ERROR, message=str(e))
                if self.proxy is not None:
                    self.proxy.terminate()

            ###########################################################################################

            finally:
                if err:
                    logger.error(err)
                    # reset proxy
                    self.proxy = None

        # if the dropbot is already connected
        else:
            logger.info(f"Dropbot already connected on port {port_name}")

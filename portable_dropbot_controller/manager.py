import json
import logging
from threading import Event

import dramatiq
import serial.tools.list_ports as lsp
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED, STATE_PAUSED
from apscheduler.triggers.interval import IntervalTrigger
from traits.api import HasTraits, Bool, Instance
from traits.has_traits import provides

from dropbot_controller.consts import (
    DROPBOT_CONNECTED,
)
from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor, \
    basic_listener_actor_routine
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase
from .consts import PORT_DROPBOT_STATUS_UPDATE, PKG
from .utils import (
    decode_login_response,
    decode_status_data,
    decode_adc_data,
)

from .portable_dropbot_sevice import DropletBotUart

from logger.logger_service import get_logger
logger = get_logger(__name__)


# ------------------------------------------------------------------
# Driver Callbacks (From Thread)
# ------------------------------------------------------------------
# --- Callback Functions ---
def _handle_ready_read(cmd, data):
    """
    This function is called when data is received from the device.
    It's the equivalent of the `slotReadyRead` in widget.cpp.
    """

    # Handle special commands (like the C++ code filters)
    # status_commands = {0x1204, 0x1104}  # Status/heartbeat messages

    # if cmd in status_commands:
    #     # Show brief status message instead of full hex dump
    #     board_name = "Signal Board" if (cmd >> 8) == 0x12 else "Driver Board"
    #     print(f"  └─ {board_name} Status (0x{cmd:04X}) - {len(data)} bytes > {data[:21].decode().strip()}")
    #     return

    if cmd >> 8 == 0x12:
        board = "Signal"
    elif cmd >> 8 == 0x11:
        board = "Motor"
    else:
        board = "Unknown"

    skip_commands = [
        0x02,
        0x03,
        0x23,
        0x24,
        0x25,
        0x26,
        0x61,
        0x71,
        0x73,
        0x80,
        0x81,
        0x82,
        0x31,
        0x33,
        0xAC,
        0xB0,
        0xB3,
        0xB4,
        0xB1,
    ]

    # Try to decode known command responses
    if cmd & 0xFF == 0x01:  # Signal board login response
        result = decode_login_response(data)
        print(f"  └─ {board} board login response: {result}")
        if "SUCCESS" in result:
            publish_message(topic=DROPBOT_CONNECTED, message=result)

    elif cmd & 0xFF == 0x04:  # Signal board version response
        result = decode_status_data(cmd, data)
        res_json = json.dumps(result)
        publish_message(res_json, PORT_DROPBOT_STATUS_UPDATE)
        logger.debug(f">>> {board} board status: {result}")
        pass
    elif cmd & 0xFF == 0x32:  # Signal board high voltage test response
        print(f"||| Channel Capacitances: {[x for x in data]}")
    elif cmd & 0xFF == 0x34:  # Signal board capacitor calibration progress response
        print(f"!!! Channel capacitance > {data[1]} / {data[0]} : {data[2]}")
    elif cmd & 0xFF == 0xA5:  # Signal board ADC data response
        print(f"ADC data: {decode_adc_data(data)}")
    elif cmd & 0xFF in skip_commands:
        return
    else:
        print(f"[<-- RECV] CMD: {cmd:04X}, Data: {data.hex(' ')}")


def _handle_error(err_code, cmd_str):
    """
    This function is called when an error is reported by the UART driver.
    """
    print(f"[ERROR] Code: {err_code}, Message: {cmd_str}")


def _handle_alarm(cmd, alarms):
    """
    This function is called when an alarm is reported by the device.
    """
    if cmd >> 8 == 0x12:
        board = "Signal"
    elif cmd >> 8 == 0x11:
        board = "Motor"
    else:
        board = "Unknown"
    print(f" {board} board reported alarms")
    for alarm in alarms:
        alarm = alarm.replace("开路", " Motor Not Connected (Open Circuit)")
        alarm = alarm.replace("原点信号一直触发", " Home signal triggered continuously")
        print(f"  └─ {alarm}")


@provides(IDramatiqControllerBase)
class ConnectionManager(HasTraits):
    """
    Manages the serial connection to the DropBot in a background thread.
    Updates trait properties which the UI/ViewModel can observe.
    """

    # --- Public Status Traits (Observed by ViewModel) ---
    connected = Bool(False)

    # --- Internal Control ---
    driver = Instance(DropletBotUart)

    monitor_scheduler = Instance(BackgroundScheduler)

    ###################################################################################
    # IDramatiqControllerBase Interface
    ###################################################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = f"{PKG}_listener"

    def traits_init(self):
        logger.info("Starting SSH controls listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.name,
            class_method=self.listener_actor_routine)

        self.driver = DropletBotUart()
        self._stop_event = Event()

        # Wire up driver callbacks to our internal handlers
        self.driver.on_ready_read = _handle_ready_read
        self.driver.on_error = _handle_error
        self.driver.on_alarm = _handle_alarm

    def listener_actor_routine(self, message, topic):
        if "dropbot" in topic.split("/")[0]:
            return basic_listener_actor_routine(self, message, topic, handler_name_pattern="_on_{topic}_request")
        else:
            return None

    # ------------------------------------------------------------------
    # Control methods dramatiq
    # ------------------------------------------------------------------
    def _on_toggle_dropbot_loading_request(self, *args, **kwargs):
        logger.info("Processing dropbot loading...")
        if self.connected:
            self.driver.setTray(not self.driver.getTray())

    # ------------------------------------------------------------------
    # Connection Control
    # ------------------------------------------------------------------
    def connect(self, port: str = None, baud: int = 115200) -> bool:
        """Attempts to connect to the hardware and starts the polling loop."""
        if self.connected:
            logger.warning("Already connected.")
            return True

        if port is None:
            port = self._auto_detect_port()
            if not port:
                logger.error("No valid port found.")
                return False

        logger.info(f"Connecting to {port} at {baud}...")
        if not self.driver.init(port, baud):
            logger.error("Failed to open serial port.")
            self.connected = False
            return False

        # Perform Handshake
        sig_resp, mot_resp = self.driver.login()
        if not (sig_resp or mot_resp):
            logger.error("Login failed (No response from either board).")
            self.driver.close()
            return False

        # Success - Update State
        self.port_name = port
        self.connected = True

        # Fetch Versions
        s_ver, m_ver = self.driver.getVersions()
        self.signal_version = s_ver or "Unknown"
        self.motor_version = m_ver or "Unknown"

        return True

    def _auto_detect_port(self):
        """Simple auto-detection strategy."""
        ports = lsp.comports()
        # Add logic here to filter by HWID if known
        return ports[0].device if ports else None

    def _on_start_device_monitoring_request(self):
        """
        Method to start looking for dropbots connected using their hwids.
        If dropbot already connected, publishes dropbot connected signal.
        """
        # if dropbot already connected, exit after publishing connection and chip details
        if self.connected:
            publish_message("dropbot_connected", DROPBOT_CONNECTED)
            return None

        ## handle cases where monitor scheduler object already exists
        if hasattr(self, "monitor_scheduler"):
            if isinstance(self.monitor_scheduler, BackgroundScheduler):

                if self.monitor_scheduler.state == STATE_RUNNING:
                    logger.warning(f"Dropbot connections are already being monitored.")

                elif self.monitor_scheduler.state == STATE_STOPPED:
                    self.monitor_scheduler.start()
                    logger.info(f"Dropbot connection monitoring started now.")

                elif self.monitor_scheduler.state == STATE_PAUSED:
                    self.monitor_scheduler.resume()
                    logger.info(
                        f"Dropbot connection monitoring was paused, now it is resumed."
                    )

                else:
                    logger.error(
                        f"Invalid dropbot monitor scheduler state: it is {self.monitor_scheduler.state}"
                    )

                return None

        def check_devices_with_error_handling():
            """
            Wrapper to handle errors from check_devices_available.
            """
            try:
                return self.connect()
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
        scheduler.add_listener(self._device_found, EVENT_JOB_EXECUTED)
        self.monitor_scheduler = scheduler

        logger.info("DropBot monitor created and started")
        # self._error_shown = False  # Reset error state when starting monitoring
        self.monitor_scheduler.start()

    ################################# Protected methods ######################################
    def _device_found(self, event):
        """
        Method defining what to do when dropbot has been found on a port.
        """
        # if check_devices did not return true => still disconnected
        if not event.retval:
            return

        logger.debug("DropBot port found")
        self.monitor_scheduler.pause()

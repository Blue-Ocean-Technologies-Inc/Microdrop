import json
from threading import Event

import dramatiq
import numpy as np
import serial.tools.list_ports as lsp
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED, STATE_PAUSED
from apscheduler.triggers.interval import IntervalTrigger
from svgwrite.data.pattern import frequency
from traits.api import HasTraits, Bool, Instance, provides, Int, Array, Range, observe

from dropbot_controller.consts import (
    DROPBOT_CONNECTED,
)
from dropbot_controller.dropbot_controller_base import app_globals
from dropbot_controller.models.dropbot_channels_properties_model import (
    DropbotChannelsPropertiesModelFromJSON,
)
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
    basic_listener_actor_routine,
)
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

CMD_RESPONSES = {}

from functools import wraps
import threading


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
    #     logger.info(f"  └─ {board_name} Status (0x{cmd:04X}) - {len(data)} bytes > {data[:21].decode().strip()}")
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
        logger.info(f"  └─ {board} board login response: {result}")
        if "SUCCESS" in result:
            publish_message(topic=DROPBOT_CONNECTED, message=result)

    elif cmd & 0xFF == 0x04:  # Signal board version response
        result = decode_status_data(cmd, data)
        res_json = json.dumps(result)
        publish_message(res_json, PORT_DROPBOT_STATUS_UPDATE)
        logger.debug(f">>> {board} board status: {result}")
        pass
    elif cmd & 0xFF == 0x32:  # Signal board high voltage test response
        logger.info(f"||| Channel Capacitances: {[x for x in data]}")
    elif cmd & 0xFF == 0x34:  # Signal board capacitor calibration progress response
        logger.info(f"!!! Channel capacitance > {data[1]} / {data[0]} : {data[2]}")
    elif cmd & 0xFF == 0xA5:  # Signal board ADC data response
        logger.info(f"ADC data: {decode_adc_data(data)}")
    elif cmd & 0xFF in skip_commands:
        return
    elif cmd == 0x1121:
        logger.info(f"[<-- RECV] CMD: {cmd:04X}, Data: {data.hex(' ')}")

        is_tray_out = bool(data[0])

        if not is_tray_out:
            # If data is 0x00 (False)
            logger.info("Tray is in")
            publish_message("in", "dropbot/requests/toggle_tray_")
        else:
            # If data is 0x01 (True)
            logger.info("tray is out")
            publish_message("out", "dropbot/requests/toggle_tray_")

    else:
        logger.info(f"[<-- RECV] CMD: {cmd:04X}, Data: {data.hex(' ')}")


def _handle_error(err_code, cmd_str):
    """
    This function is called when an error is reported by the UART driver.
    """
    logger.info(f"[ERROR] Code: {err_code}, Message: {cmd_str}")


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
    logger.info(f" {board} board reported alarms")
    for alarm in alarms:
        alarm = alarm.replace("开路", " Motor Not Connected (Open Circuit)")
        alarm = alarm.replace("原点信号一直触发", " Home signal triggered continuously")
        logger.info(f"  └─ {alarm}")


# util decorators
def require_active_driver(func):
    """
    Thread-safe decorator.
    1. Acquires self._driver_lock.
    2. Checks if self.driver exists.
    3. Runs the function if safe, otherwise logs an error.
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Ensure the lock exists (defensive programming)
        if not hasattr(self, "_driver_lock"):
            self._driver_lock = threading.RLock()

        with self._driver_lock:
            # Standard check for driver availability
            if not hasattr(self, "driver") or self.driver is None:
                # Use the function name to make the log useful
                operation = func.__name__.replace("_", " ").strip()
                logger.error(f"Driver not available for: {operation}")
                return

            # If we get here, it is safe to run the actual logic
            return func(self, *args, **kwargs)

    return wrapper


def require_realtime_mode(func):
    """
    Thread-safe decorator.
    1. Acquires self._driver_lock.
    2. Checks if self.driver exists.
    3. Runs the function if safe, otherwise logs an error.
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Ensure the lock exists (defensive programming)
        if not self.realtime_mode:
            # Use the function name to make the log useful
            operation = func.__name__.replace("_", " ").strip()
            logger.warning(
                f"Realtime mode not enabled for {self}. Cannot perform {operation} "
            )
            return

        # If we get here, it is safe to run the actual logic
        return func(self, *args, **kwargs)

    return wrapper


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

    voltage = Range(30, 200)
    frequency = Range(50, 60_000)
    realtime_mode = Bool
    channel_states_arr = Array

    ###################################################################################
    # IDramatiqControllerBase Interface
    ###################################################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = f"{PKG}_listener"

    def traits_init(self):
        logger.info("Starting Portable dropbot controls listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.name, class_method=self.listener_actor_routine
        )

        self.driver = DropletBotUart()
        self._stop_event = Event()

        # Wire up driver callbacks to our internal handlers
        self.driver.on_ready_read = _handle_ready_read
        self.driver.on_error = _handle_error
        self.driver.on_alarm = _handle_alarm

        self._driver_lock = threading.RLock()

    def listener_actor_routine(self, message, topic):
        if "dropbot" in topic.split("/")[0]:
            return basic_listener_actor_routine(
                self, message, topic, handler_name_pattern="_on_{topic}_request"
            )
        else:
            return None

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

    ######## Request handlers ####################################################

    def _on_start_device_monitoring_request(self, *args, **kwargs):
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

    # ------------------------------------------------------------------
    # Control methods dramatiq
    # ------------------------------------------------------------------
    @require_active_driver
    def _on_toggle_tray_request(self, *args, **kwargs):
        logger.critical("Processing dropbot loading...")
        self.driver.getTray()

    @require_active_driver
    def _on_toggle_tray__request(self, msg):
        logger.debug("Processing dropbot loading... Recieved response from dropbot")
        if msg == "out":
            logger.info("requesting tray to go in")
            self.driver.setTray(0)
        elif msg == "in":
            logger.info("requesting tray to go out")
            self.driver.setTray(1)

    # @require_active_driver
    def _on_electrodes_state_change_request(self, message):
        # 1. Validation (Safe to do inside lock for simplicity)
        try:

            channel_states_map_model = DropbotChannelsPropertiesModelFromJSON(
                num_available_channels=120,
                property_dtype=bool,
                channels_properties_json=message,
            ).model

            if len(channel_states_map_model.channels_properties_array) != 120:
                logger.error("Boolean mask size mismatch: expected 120")
                return

            if not np.array_equal(
                channel_states_map_model.channels_properties_array,
                self.channel_states_arr,
            ):
                self.channel_states_arr = (
                    channel_states_map_model.channels_properties_array
                )

        except Exception as e:
            logger.error(f"Error validating electrode message: {e}")
            return

    @observe("channel_states_arr")
    @require_realtime_mode
    @require_active_driver
    def _actuate_electrodes(self, event=None):
        # 2. Hardware Action (Driver is guaranteed to exist here)
        self.driver.setElectrodeStates(self.channel_states_arr)
        app_globals["last_channel_states_requested"] = self.channel_states_arr

    def _on_set_voltage_request(self, message):
        try:
            self.voltage = int(message)
        except Exception as e:
            logger.error(f"Cannot request voltage {self.voltage} V: {e}", exc_info=True)

    @observe("voltage")
    @require_realtime_mode
    @require_active_driver
    def _voltage_change(self, event):
        if event.new != event.old:
            self.driver.voltage = event.new
            logger.info(f"Set voltage to {self.voltage} V")

    def _on_set_frequency_request(self, message):
        try:
            self.frequency = int(message)
        except Exception as e:
            logger.error(f"Cannot request frequency {frequency}: {e}", exc_info=True)

    @observe("frequency")
    @require_realtime_mode
    @require_active_driver
    def _frequency_change(self, event):
        if event.new != event.old:
            self.driver.frequency = event.new
            logger.info(f"Set frequency to {self.frequency} Hz")

    def _on_set_realtime_mode_request(self, message):
        realtime_mode = message.lower() == "true"

        if realtime_mode != self.realtime_mode:
            self.realtime_mode = realtime_mode

            ## apply stored values i true
            if self.realtime_mode:
                self.driver.voltage = self.voltage
                self.driver.frequency = self.frequency
                self.driver.setElectrodeStates(self.channel_states_arr)

            else:
                self.driver.setElectrodeStates(self.channel_states_arr * 0)

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

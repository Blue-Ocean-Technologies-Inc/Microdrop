import json
from threading import Event

import dramatiq
import numpy as np
import serial.tools.list_ports as lsp
from apptools.preferences.i_preferences import IPreferences
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED, STATE_PAUSED
from apscheduler.triggers.interval import IntervalTrigger
from peripheral_controller.preferences import PeripheralPreferences

from dropbot_controller.preferences import DropbotPreferences
from svgwrite.data.pattern import frequency
from traits.api import HasTraits, Bool, Instance, provides, Int, Array, Range, observe, Dict

from dropbot_controller.consts import (
    DROPBOT_CONNECTED,
    CHIP_INSERTED,
    VOLTAGE_LIM,
    FREQUENCY_LIM,
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
from peripheral_controller.consts import CONNECTED, ZSTAGE_POSITION_UPDATED
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
    # elif cmd == 0x1121:
    #     logger.info(f"[<-- RECV] CMD: {cmd:04X}, Data: {data.hex(' ')}")
    #
    #     is_tray_out = bool(data[0])
    #
    #     if not is_tray_out:
    #         # If data is 0x00 (False)
    #         logger.info("Tray is in")
    #         publish_message("in", "dropbot/requests/toggle_tray_")
    #     else:
    #         # If data is 0x01 (True)
    #         logger.info("tray is out")
    #         publish_message("out", "dropbot/requests/toggle_tray_")

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

    # -- preferences
    app_preferences = Instance(IPreferences)

    # --- Internal Control ---
    driver = Instance(DropletBotUart)

    monitor_scheduler = Instance(BackgroundScheduler)

    voltage = Range(VOLTAGE_LIM[0], VOLTAGE_LIM[1])
    frequency = Range(FREQUENCY_LIM[0], FREQUENCY_LIM[1])

    light_intensity = Range(0, 100)
    realtime_mode = Bool
    channel_states_arr = Array

    driver_params = Dict

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

        self.dropbot_preferences = DropbotPreferences(preferences=self.app_preferences)
        self.peripheral_preferences = PeripheralPreferences(preferences=self.app_preferences)

    def listener_actor_routine(self, message, topic):
        logger.debug(message, topic)
        return basic_listener_actor_routine(self, message, topic, handler_name_pattern="_on_{topic}_request")
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
        # get params
        self.driver_params = self.driver.getParams()

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
            self._send_device_status_update()
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

        # check if tray and the pogo are home
        if self._check_tray_home() and self._check_pogo_home():
            logger.info("Both the tray and pogo are home: chip is loaded. Getting it out")
            self.driver.setTray(1)
            publish_message("False", CHIP_INSERTED)
        else:
            logger.info("One of the tray or pogo motors are not homed. Setting them in")
            self.driver.setTray(0)
            publish_message("True", CHIP_INSERTED)

    @require_active_driver
    def _on_lock_chip_request(self, message):
        logger.critical("Processing dropbot loading...")

        request = message.lower() == "true"

        if request:
            self.driver.setPogo(1)
            publish_message("True", CHIP_INSERTED)

        else:
            self.driver.setPogo(0)
            publish_message("False", CHIP_INSERTED)

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
            self.voltage = int(float(message))
            self.dropbot_preferences.default_voltage = self.voltage
        except Exception as e:
            logger.error(f"Cannot request voltage {self.voltage} V: {e}", exc_info=True)

    @observe("voltage")
    @require_realtime_mode
    @require_active_driver
    def _voltage_change(self, event):
        self.driver.voltage = event.new
        logger.info(f"Set voltage to {self.voltage} V")

    def _on_set_frequency_request(self, message):
        try:
            self.frequency = int(float(message))
            self.dropbot_preferences.default_frequency = self.frequency
        except Exception as e:
            logger.error(f"Cannot request frequency {frequency}: {e}", exc_info=True)

    @observe("frequency")
    @require_realtime_mode
    @require_active_driver
    def _frequency_change(self, event):
        self.driver.frequency = event.new
        logger.info(f"Set frequency to {self.frequency} Hz")

    def _on_set_light_intensity_request(self, message):
        try:
            self.light_intensity = int(message)
            self.peripheral_preferences.default_light_intensity = self.light_intensity
        except Exception as e:
            logger.error(f"Cannot request light intensity {self.light_intensity} %: {e}", exc_info=True)

    @observe("light_intensity")
    @require_active_driver
    def _light_intensity_change(self, event):
        self.driver.setLEDIntensity(int(event.new))
        logger.info(f"Set light intensity to {self.light_intensity}%")

    def _on_set_realtime_mode_request(self, message):
        realtime_mode = message.lower() == "true"

        if realtime_mode != self.realtime_mode:
            self.realtime_mode = realtime_mode

            ## apply stored values i true
            if self.realtime_mode:
                self.driver.voltage = self.voltage
                self.driver.frequency = self.frequency
                self.driver.setLEDIntensity(self.light_intensity)
                self.driver.setElectrodeStates(self.channel_states_arr)

            else:
                self.driver.setElectrodeStates(self.channel_states_arr * 0)

    @require_active_driver
    def _on_motor_home_request(self, motor_id):
        logger.critical(f"Homing Motor {motor_id}...")
        self.driver.motorHome(motor_id)

        if motor_id == "magnet":
            publish_message(
                str(self.driver_params.get("motor_board", {}).get("magnet_defaults", {}).get("z_down", 0) / 1000),
                ZSTAGE_POSITION_UPDATED
            )

    @require_active_driver
    def _on_motor_relative_move_request(self, message):

        msg = json.loads(message)

        motor_id = msg.get("motor_id")
        move_distance = msg.get("move_distance")

        self.driver.motorRelativeMove(motor_id, move_distance)

    @require_active_driver
    def _on_motor_absolute_move_request(self, message):

        msg = json.loads(message)

        motor_id = msg.get("motor_id")
        move_distance = msg.get("move_distance")

        self.driver.motorAbsoluteMove(motor_id, move_distance)

    @require_active_driver
    def _on_toggle_motor_request(self, message) -> None:
        """
        Handles requests to set a motor to a specific abstract 'state' (index or boolean).
        Resolves the actual absolute position using loaded driver parameters.
        """
        logger.critical(message)
        try:
            msg = json.loads(message)
            motor_id = msg.get("motor_id")
            # 'state' can be an integer index (for PMT/Filter) or boolean (for Tray/Magnet)
            state = int(msg.get("state"))

            # 1. Get the configuration for the motor board
            params = self.driver_params.get("motor_board", {})
            target_pos = None

            # 2. Resolve target position based on Motor ID

            # --- TRAY (ID 0) ---
            if motor_id == "tray":
                defaults = params.get("tray_defaults", {})
                # State 1 = Out, State 0 = In
                target_pos = (
                    defaults.get("out_pos") if state else defaults.get("in_pos")
                )

            # --- PMT (ID 1) ---
            elif motor_id == "pmt":
                defaults = params.get("pmt_defaults", {})
                # State is the index (0-4), key format is 'pmt_pos_X'
                target_pos = defaults.get(f"pmt_pos_{int(state)}")

            # --- MAGNET (ID 2) ---
            elif motor_id == "magnet":
                defaults = params.get("magnet_defaults", {})
                target_pos = defaults.get("z_down") if state else defaults.get("z_up")

                self.driver.motorAbsoluteMove(motor_id, int(target_pos))
                publish_message(str(target_pos / 1000), ZSTAGE_POSITION_UPDATED)

                return None

            # --- FILTER (ID 3) ---
            elif motor_id == "filter":
                defaults = params.get("filter_defaults", {})
                # State is the index (0-4), key format is 'filter_pos_X'
                target_pos = defaults.get(f"filter_pos_{int(state)}")

            # --- POGO LEFT (ID 4) & RIGHT (ID 5) ---
            elif "pogo" in motor_id:
                down_pos = params.get("pogo_defaults", 2250)
                target_pos = down_pos if state else 0

            # 3. Execute the Move
            if target_pos is not None:
                logger.info(
                    f"Setting ID = {motor_id} to State {state} -> {target_pos}um"
                )
                self.driver.motorAbsoluteMove(motor_id, int(target_pos))
            else:
                logger.error(
                    f"Could not resolve position for ID = {motor_id} with state '{state}'",
                    exc_info=True
                )

        except Exception as e:
            logger.error(f"Error processing toggle motor request: {e}", exc_info=True)

    ######## Z Stage Topic Handlers ########################################

    @require_active_driver
    @require_realtime_mode
    def _on_go_home_request(self, message):
        """
        Home z stage
        """
        self._on_motor_home_request("magnet")

    @require_active_driver
    @require_realtime_mode
    def _on_move_up_request(self, message):
        """
        Move up z stage
        """
        self._on_toggle_motor_request(json.dumps({"motor_id": "magnet", "state": 0}))

    @require_active_driver
    @require_realtime_mode
    def _on_move_down_request(self, message):
        """
        Move down z stage
        """
        self._on_toggle_motor_request(json.dumps({"motor_id": "magnet", "state": 1}))

    @require_active_driver
    @require_realtime_mode
    def _on_set_position_request(self, message):
        """
        Move z stage to position. Received message is the distance in mm (milli meters)
        """
        logger.info(f"Moving magnet to {message}mm position")
        self.driver.motorAbsoluteMove("magnet", int(float(message) * 1000))
        publish_message(message, ZSTAGE_POSITION_UPDATED)

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

        self._send_device_status_update()

    def _send_device_status_update(self):

        chip_inserted = self._check_pogo_home() and self._check_tray_home()

        publish_message("", DROPBOT_CONNECTED)

        if  chip_inserted:
            publish_message("True", CHIP_INSERTED)
        else:
            publish_message("False", CHIP_INSERTED)

    def _check_pogo_home(self):
        motor_pos = self.driver.getMotorPositions()
        pogo_left = motor_pos.get("pogo_left")
        pogo_right = motor_pos.get("pogo_right")

        total_pogo_pos = pogo_left + pogo_right

        expected_home_pos = self.driver_params.get("motor_board").get("pogo_defaults") * 2

        return total_pogo_pos == expected_home_pos

    def _check_tray_home(self):
        motor_pos = self.driver.getMotorPositions()

        tray_pos = motor_pos.get("tray")
        expected_home_pos = self.driver_params.get("motor_board").get("tray_defaults").get("in_pos")

        return tray_pos == expected_home_pos

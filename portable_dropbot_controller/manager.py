import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event

import dramatiq
import numpy as np
import serial.tools.list_ports as lsp
from apptools.preferences.i_preferences import IPreferences
from apscheduler.events import EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED, STATE_PAUSED
from apscheduler.triggers.date import DateTrigger
from peripheral_controller.preferences import PeripheralPreferences

from dropbot_controller.preferences import DropbotPreferences
from traits.api import HasTraits, Bool, Instance, provides, Array, Range, observe, Dict

from dropbot_controller.consts import (
    DROPBOT_CONNECTED,
    DROPBOT_DISCONNECTED,
    CHIP_INSERTED,
    TRAY_TOGGLE_FAILED,
    CHIP_LOCK_FAILED,
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
from peripheral_controller.consts import ZSTAGE_POSITION_UPDATED
from .consts import (
    PORT_DROPBOT_STATUS_UPDATE,
    PORT_DROPBOT_DIAGNOSTICS_RESULT,
    PORT_DROPBOT_TEMPERATURE_UPDATE,
    PORT_DROPBOT_SWEEP_RESULT,
    PORT_DROPBOT_DROPS_RESULT,
    PORT_DROPBOT_CAPACITANCE_RESULT,
    PKG,
)
from .utils import (
    decode_login_response,
    decode_status_data,
    decode_adc_data,
)

from .portable_dropbot_service import DropletBotUart
from .session import DropletBotSession, DropletBotError
from .commands import SignalBoard

from logger.logger_service import get_logger

logger = get_logger(__name__)

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
    elif cmd & 0xFF == 0x32:  # Signal board high voltage test response
        logger.info(f"||| Channel Capacitances: {[x for x in data]}")
    elif cmd & 0xFF == 0x34:  # Signal board capacitor calibration progress response
        logger.info(f"!!! Channel capacitance > {data[1]} / {data[0]} : {data[2]}")
    elif cmd & 0xFF == 0xA5:  # Signal board ADC data response
        logger.info(f"ADC data: {decode_adc_data(data)}")
    elif cmd & 0xFF in skip_commands:
        return
    else:
        logger.info(f"[<-- RECV] CMD: {cmd:04X}, Data: {data.hex(' ')}")


def _handle_error(err_code, cmd_str):
    """
    Module-level fallback when no manager is wired. Called when an error
    is reported by the UART driver.
    """
    logger.error(f"[ERROR] Code: {err_code}, Message: {cmd_str}")


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
            if getattr(self, "_shutting_down", False):
                return
            if not hasattr(self, "driver") or self.driver is None:
                operation = func.__name__.replace("_", " ").strip()
                logger.error(f"Driver not available for: {operation}")
                return
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


def run_in_background(func):
    """
    Run a (potentially long) handler on the manager's single-worker task
    executor instead of the calling dramatiq actor thread, so the actor
    returns immediately.

    Tasks are serialized (max_workers=1), and driver access inside the task
    is still protected by require_active_driver's lock, so concurrent serial
    transactions cannot interleave. Falls back to inline execution if the
    executor is unavailable (e.g. during shutdown).
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        executor = getattr(self, "_task_executor", None)
        if executor is None or getattr(self, "_shutting_down", False):
            return func(self, *args, **kwargs)

        def _job():
            try:
                func(self, *args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Background task '{func.__name__}' failed: {e}", exc_info=True
                )

        try:
            executor.submit(_job)
        except RuntimeError:
            # Executor already shut down; run inline as a last resort.
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

    voltage = Range(
        VOLTAGE_LIM[0], VOLTAGE_LIM[1], value=DropbotPreferences().default_voltage, #TODO: May need to give as input application preferences.
        desc="the voltage to set on the dropbot device (V)"
    )
    frequency = Range(
        FREQUENCY_LIM[0], FREQUENCY_LIM[1], value=DropbotPreferences().default_frequency, #TODO: May need to give as input application preferences.
        desc="the frequency to set on the dropbot device (Hz)"
    )

    # Light Controls
    light_intensity = Range(
        0,
        100,
        value=PeripheralPreferences().default_light_intensity,
        desc="Light intensity percentage",
    )
    realtime_mode = Bool(False)
    channel_states_arr = Array

    driver_params = Dict

    ###################################################################################
    # IDramatiqControllerBase Interface
    ###################################################################################

    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = f"{PKG}_listener"

    def _handle_driver_error(self, err_code, cmd_str):
        """Handle UART driver errors (e.g. serial disconnect). Attempt reconnect only when UART breaks."""
        logger.error(f"[ERROR] Code: {err_code}, Message: {cmd_str}")
        if self.connected:
            self.connected = False
            publish_message("", DROPBOT_DISCONNECTED)
            # Defer close+resume so we don't deadlock (callback runs from driver's listen thread)

            def _attempt_reconnect():
                import time
                time.sleep(0.5)
                if getattr(self, "_shutting_down", False):
                    return
                try:
                    self.driver.close()
                except Exception as e:
                    logger.warning(f"Driver close during reconnect: {e}")
                if (
                    hasattr(self, "monitor_scheduler")
                    and self.monitor_scheduler is not None
                    and self.monitor_scheduler.state == STATE_PAUSED
                ):
                    logger.info("UART broken. Resuming monitor to attempt reconnection.")
                    self.monitor_scheduler.resume()

            threading.Thread(target=_attempt_reconnect, daemon=True).start()

    def traits_init(self):
        logger.info("Starting Portable dropbot controls listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.name, class_method=self.listener_actor_routine
        )

        self.driver = DropletBotUart()
        self._stop_event = Event()

        # High-level session API (self-test, ramp, drops, feedback actuation,
        # sweep, ...) bound to the SAME live, manager-owned driver. Constructed
        # without a port so it does not open its own serial connection; we then
        # rebind its UART to the managed driver.
        self.session = DropletBotSession()
        self.session._uart = self.driver

        # Wire up driver callbacks to our internal handlers
        self.driver.on_ready_read = _handle_ready_read
        self.driver.on_error = self._handle_driver_error
        self.driver.on_alarm = _handle_alarm

        self._driver_lock = threading.RLock()
        self._shutting_down = False
        self._error_shown = False
        # Single-worker executor for long-running session ops (self-test,
        # sweeps, feedback actuation) so they don't block the dramatiq actor.
        self._task_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="dropbot-task"
        )
        self.channel_states_arr = np.zeros(120, dtype=bool)

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

        if sig_resp:
            self._sync_signal_board_settings_on_login()

        # Fetch Versions
        s_ver, m_ver = self.driver.getVersions()
        self.signal_version = s_ver or "Unknown"
        self.motor_version = m_ver or "Unknown"

        return True

    @require_active_driver
    def _sync_signal_board_settings_on_login(self):
        """
        Ensure signal board uses the currently selected defaults after login.
        """
        self.driver.voltage = self.voltage
        self.driver.frequency = self.frequency
        logger.info(
            f"Applied signal-board settings after login: {self.voltage} V, {self.frequency} Hz"
        )

    def _auto_detect_port(self):
        """Auto-detect port, preferring DropBot HWID when known."""
        from dropbot_controller.consts import DROPBOT_DB3_120_HWID

        ports = lsp.comports()
        if not ports:
            return None
        # Prefer DropBot VID:PID if present
        for p in ports:
            if hasattr(p, "hwid") and p.hwid and DROPBOT_DB3_120_HWID in p.hwid:
                return p.device
        return ports[0].device

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

        MONITOR_INTERVAL_BASE = 2
        MONITOR_INTERVAL_MAX = 60

        def check_devices_with_error_handling():
            """
            Try to connect; on failure, reschedule with exponential backoff.
            """
            try:
                result = self.connect()
                if result:
                    self._consecutive_failures = 0
                return result
            except Exception as e:
                if not self._error_shown:
                    logger.error(f"{str(e)}")
                    self._error_shown = True
                return None

        def scheduled_check():
            result = check_devices_with_error_handling()
            if result:
                return
            if getattr(self, "_shutting_down", False):
                return
            if not hasattr(self, "monitor_scheduler") or self.monitor_scheduler is None:
                return
            self._consecutive_failures = getattr(self, "_consecutive_failures", 0) + 1
            delay_sec = min(
                MONITOR_INTERVAL_BASE * (2 ** min(self._consecutive_failures - 1, 5)),
                MONITOR_INTERVAL_MAX,
            )
            run_date = datetime.now() + timedelta(seconds=delay_sec)
            self.monitor_scheduler.add_job(
                scheduled_check,
                trigger=DateTrigger(run_date=run_date),
                id="connection_check",
                replace_existing=True,
            )

        scheduler = BackgroundScheduler()
        scheduler.add_listener(self._device_found, EVENT_JOB_EXECUTED)
        self.monitor_scheduler = scheduler
        self._consecutive_failures = 0
        self._error_shown = False

        scheduler.add_job(
            scheduled_check,
            trigger=DateTrigger(run_date=datetime.now() + timedelta(seconds=MONITOR_INTERVAL_BASE)),
            id="connection_check",
        )

        logger.info("DropBot monitor created and started")
        self.monitor_scheduler.start()

    # ------------------------------------------------------------------
    # Control methods dramatiq
    # ------------------------------------------------------------------
    @require_active_driver
    def _on_toggle_tray_request(self, *args, **kwargs):
        if not self.connected:
            logger.warning("Tray toggle ignored: DropBot not connected.")
            publish_message("true", TRAY_TOGGLE_FAILED)
            return
        logger.info("Processing dropbot tray toggle...")

        try:
            tray_home, pogo_home = self._check_tray_and_pogo_home()
            if tray_home and pogo_home:
                logger.info("Both the tray and pogo are home: chip is loaded. Getting it out")
                # setTray returns True on error, False on success
                err = self.driver.setTray(1)
                if not err:
                    publish_message("False", CHIP_INSERTED)
                else:
                    logger.error("Tray move (out) failed")
                    publish_message("true", TRAY_TOGGLE_FAILED)
            else:
                logger.info("One of the tray or pogo motors are not homed. Setting them in")
                err = self.driver.setTray(0)
                if not err:
                    publish_message("True", CHIP_INSERTED)
                else:
                    logger.error("Tray move (in) failed")
                    publish_message("true", TRAY_TOGGLE_FAILED)
        except Exception as e:
            logger.error(f"Tray toggle failed: {e}", exc_info=True)
            publish_message("true", TRAY_TOGGLE_FAILED)

    @require_active_driver
    def _on_lock_chip_request(self, message):
        if not self.connected:
            logger.warning("Lock chip ignored: DropBot not connected.")
            publish_message("true", CHIP_LOCK_FAILED)
            return
        logger.info("Processing dropbot chip lock...")

        content = str(message) if message is not None else ""
        request = content.lower() == "true"

        if request:
            ok = self.driver.setPogo(1)
            if ok:
                publish_message("True", CHIP_INSERTED)
            else:
                logger.error("Set pogo down failed")
                publish_message("true", CHIP_LOCK_FAILED)
        else:
            ok = self.driver.setPogo(0)
            if ok:
                publish_message("False", CHIP_INSERTED)
            else:
                logger.error("Set pogo up failed")
                publish_message("true", CHIP_LOCK_FAILED)

    # @require_active_driver
    def _on_electrodes_state_change_request(self, message):
        # 1. Validation (Safe to do inside lock for simplicity)
        try:
            content = str(message) if message is not None else "{}"
            channel_states_map_model = DropbotChannelsPropertiesModelFromJSON(
                num_available_channels=120,
                property_dtype=bool,
                channels_properties_json=content,
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
            content = str(message) if message is not None else "0"
            self.voltage = int(float(content))
        except Exception as e:
            logger.error(f"Cannot request voltage {self.voltage} V: {e}", exc_info=True)

    @observe("voltage")
    @require_realtime_mode
    @require_active_driver
    def _voltage_change(self, event):
        self.dropbot_preferences.default_voltage = self.voltage
        self.driver.voltage = event.new
        logger.info(f"Set voltage to {self.voltage} V")

    def _on_set_frequency_request(self, message):
        try:
            content = str(message) if message is not None else "0"
            self.frequency = int(float(content))
        except Exception as e:
            logger.error(f"Cannot request frequency {message}: {e}", exc_info=True)

    @observe("frequency")
    @require_realtime_mode
    @require_active_driver
    def _frequency_change(self, event):
        self.dropbot_preferences.default_frequency = self.frequency
        self.driver.frequency = event.new
        logger.info(f"Set frequency to {self.frequency} Hz")

    def _on_set_light_intensity_request(self, message):
        try:
            content = str(message) if message is not None else "0"
            self.light_intensity = int(content)
        except Exception as e:
            logger.error(f"Cannot request light intensity {self.light_intensity} %: {e}", exc_info=True)

    @observe("light_intensity")
    @require_active_driver
    def _light_intensity_change(self, event):
        self.peripheral_preferences.default_light_intensity = self.light_intensity
        self.driver.setLEDIntensity(int(event.new))
        logger.info(f"Set light intensity to {self.light_intensity}%")

    def _on_set_realtime_mode_request(self, message):
        content = str(message) if message is not None else ""
        realtime_mode = content.lower() == "true"

        if realtime_mode != self.realtime_mode:
            self.realtime_mode = realtime_mode

            ## apply stored values if true
        arr = self.channel_states_arr
        if arr is not None and len(arr) > 0:
            if self.realtime_mode:
                self._sync_driver_to_model()
                self.driver.setElectrodeStates(arr)
            else:
                self.driver.setElectrodeStates(arr * 0)
        else:
            self.driver.setElectrodeStates(np.zeros(120, dtype=bool))

    def _sync_driver_to_model(self):
        ## apply stored values
        self.driver.voltage = self.voltage
        self.driver.frequency = self.frequency
        self.driver.setLEDIntensity(self.light_intensity)

    @require_active_driver
    def _on_motor_home_request(self, motor_id):
        motor_id = str(motor_id).strip() if motor_id is not None else ""
        if not motor_id:
            logger.error("Motor home request missing motor_id")
            return
        logger.info(f"Homing motor {motor_id}...")
        self.driver.motorHome(motor_id)

        if motor_id == "magnet":
            params = self.driver_params.get("motor_board") or {}
            defaults = params.get("magnet_defaults") or {}
            z_down = defaults.get("z_down", 0)
            publish_message(str(z_down / 1000), ZSTAGE_POSITION_UPDATED)

    @require_active_driver
    def _on_motor_relative_move_request(self, message):
        try:
            content = str(message) if message is not None else "{}"
            msg = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid motor relative move message: {e}")
            return
        motor_id = msg.get("motor_id")
        move_distance = msg.get("move_distance")
        if motor_id is None or move_distance is None:
            logger.error("motor_relative_move missing motor_id or move_distance")
            return
        self.driver.motorRelativeMove(motor_id, move_distance)

    @require_active_driver
    def _on_motor_absolute_move_request(self, message):
        try:
            content = str(message) if message is not None else "{}"
            msg = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid motor absolute move message: {e}")
            return
        motor_id = msg.get("motor_id")
        move_distance = msg.get("move_distance")
        if motor_id is None or move_distance is None:
            logger.error("motor_absolute_move missing motor_id or move_distance")
            return
        self.driver.motorAbsoluteMove(motor_id, move_distance)

    @require_active_driver
    def _on_toggle_motor_request(self, message) -> None:
        """
        Handles requests to set a motor to a specific abstract 'state' (index or boolean).
        Resolves the actual absolute position using loaded driver parameters.
        """
        logger.debug(message)
        try:
            content = str(message) if message is not None else "{}"
            msg = json.loads(content)
            motor_id = msg.get("motor_id")
            state_val = msg.get("state")
            if motor_id is None:
                logger.error("toggle_motor missing motor_id")
                return
            if state_val is None:
                logger.error("toggle_motor missing state")
                return
            state = int(state_val)

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
                if target_pos is not None:
                    self.driver.motorAbsoluteMove(motor_id, int(target_pos))
                    publish_message(str(target_pos / 1000), ZSTAGE_POSITION_UPDATED)
                else:
                    logger.error("toggle_motor magnet: missing z_down/z_up in magnet_defaults")
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
        try:
            content = str(message) if message is not None else "0"
            pos_mm = float(content)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid position request '{message}': {e}")
            return
        logger.info(f"Moving magnet to {pos_mm}mm position")
        self.driver.motorAbsoluteMove("magnet", int(pos_mm * 1000))
        publish_message(content, ZSTAGE_POSITION_UPDATED)

    ######## Session-API request handlers ###################################
    # All of these block in the dramatiq actor thread for the duration of the
    # operation (matching the existing tray/motor handlers). They drive the
    # high-level session API bound to the live driver.

    @staticmethod
    def _msg_to_dict(message) -> dict:
        """Parse an incoming message into a dict. Scalars become {'value': x}."""
        if message is None:
            return {}
        content = str(message).strip()
        if not content:
            return {}
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"value": content}
        return data if isinstance(data, dict) else {"value": data}

    @staticmethod
    def _msg_to_bool(value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        content = str(value).strip().lower()
        if content in ("true", "1", "on", "yes"):
            return True
        if content in ("false", "0", "off", "no"):
            return False
        return default

    # --- Diagnostics & detection ---
    @run_in_background
    @require_active_driver
    def _on_self_test_request(self, message=None):
        if not self.connected:
            logger.warning("Self-test ignored: DropBot not connected.")
            return
        params = self._msg_to_dict(message)
        try:
            results = self.session.self_test_electrodes(
                switch_time_ms=int(params.get("switch_time_ms", 20)),
                thresholds=params.get("thresholds"),
            )
        except Exception as e:
            logger.error(f"Self-test failed: {e}", exc_info=True)
            return
        failed = sorted(ch for ch, r in results.items() if not r["passed"])
        logger.info(f"Self-test complete: {len(failed)} failed channel(s)")
        publish_message(
            json.dumps({
                "type": "self_test",
                "passed": len(results) - len(failed),
                "failed_channels": failed,
                "results": {str(ch): r for ch, r in results.items()},
            }),
            PORT_DROPBOT_DIAGNOSTICS_RESULT,
        )

    @run_in_background
    @require_active_driver
    def _on_short_circuit_scan_request(self, message=None):
        if not self.connected:
            return
        scan = self.driver.short_circuit_detect()
        if scan is None:
            logger.error("Short-circuit scan returned no data")
            return
        shorted = [i for i, v in enumerate(scan) if v]
        logger.info(f"Short-circuit scan: {len(shorted)} shorted channel(s)")
        publish_message(
            json.dumps({"type": "short_circuit_scan", "shorted_channels": shorted}),
            PORT_DROPBOT_DIAGNOSTICS_RESULT,
        )

    @require_active_driver
    def _on_detect_shorts_request(self, message=None):
        """Chip-on-pad presence + short detection (single quick check)."""
        if not self.connected:
            return
        chip_loaded, short = self.session.detect_shorts()
        publish_message(
            json.dumps({"type": "detect_shorts", "chip_on_pad": chip_loaded, "short": short}),
            PORT_DROPBOT_DIAGNOSTICS_RESULT,
        )
        # Keep chip-inserted UI state in sync with detected presence
        publish_message("True" if chip_loaded else "False", CHIP_INSERTED)

    @run_in_background
    @require_active_driver
    def _on_calibrate_capacitors_request(self, message=None):
        if not self.connected:
            return
        result = self.session.calibrate()
        publish_message(
            json.dumps({"type": "calibrate_capacitors", "result": result}),
            PORT_DROPBOT_DIAGNOSTICS_RESULT,
        )

    @require_active_driver
    def _on_measure_capacitance_request(self, message=None):
        """Measure active-electrode capacitance with full signal-quality stats."""
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        n_averages = int(params.get("n_averages", 1))
        stats = self.session.measure_active_capacitance_stats(n_averages)
        publish_message(
            json.dumps({
                "type": "measure_capacitance",
                "n_averages": n_averages,
                "result": stats,
            }),
            PORT_DROPBOT_CAPACITANCE_RESULT,
        )

    # --- Feedback-controlled actuation ---
    @run_in_background
    @require_active_driver
    @require_realtime_mode
    def _on_ramp_voltage_request(self, message):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        target_v = params.get("target_v", params.get("value"))
        if target_v is None:
            logger.error("ramp_voltage missing target_v")
            return
        self.session.ramp_voltage(
            float(target_v),
            start_v=params.get("start_v"),
            step_v=float(params.get("step_v", 5.0)),
            delay_s=float(params.get("delay_s", 0.05)),
        )
        logger.info(f"Ramped voltage to {target_v} V")

    @run_in_background
    @require_active_driver
    def _on_calibrate_baseline_request(self, message=None):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        baseline = self.session.calibrate_baseline(
            switch_time_ms=int(params.get("switch_time_ms", 20))
        )
        publish_message(
            json.dumps({"type": "calibrate_baseline", "channels": len(baseline)}),
            PORT_DROPBOT_DIAGNOSTICS_RESULT,
        )

    @run_in_background
    @require_active_driver
    def _on_detect_drops_request(self, message=None):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        try:
            drops = self.session.detect_drops(
                channels=params.get("channels"),
                threshold_pf=float(params.get("threshold_pf", 5.0)),
                switch_time_ms=int(params.get("switch_time_ms", 20)),
            )
        except DropletBotError as e:
            logger.error(f"detect_drops: {e}")
            return
        present = sorted(ch for ch, has in drops.items() if has)
        publish_message(
            json.dumps({"type": "detect_drops", "drops": present}),
            PORT_DROPBOT_DROPS_RESULT,
        )

    @run_in_background
    @require_active_driver
    @require_realtime_mode
    def _on_actuate_and_verify_request(self, message):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        channels = params.get("channels")
        if not channels:
            logger.error("actuate_and_verify missing channels")
            return
        ok = self.session.actuate_and_verify(
            channels,
            expected_pf=float(params.get("expected_pf", 10.0)),
            max_retries=int(params.get("max_retries", 3)),
            voltage_step_v=float(params.get("voltage_step_v", 10.0)),
            initial_voltage_v=float(params.get("initial_voltage_v", 50.0)),
            frequency_hz=int(params.get("frequency_hz", 10000)),
        )
        publish_message(
            json.dumps({"type": "actuate_and_verify", "channels": channels, "success": bool(ok)}),
            PORT_DROPBOT_DIAGNOSTICS_RESULT,
        )

    # --- Temperature control ---
    @require_active_driver
    def _on_set_temperature_request(self, message):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        target = params.get("target_c", params.get("value"))
        if target is None:
            logger.error("set_temperature missing target_c")
            return
        channel = int(params.get("channel", 0))
        self.session.set_temperature(
            float(target), enable=self._msg_to_bool(params.get("enable", True), True),
            channel=channel,
        )
        logger.info(f"Heater ch{channel} target set to {target} C")

    @require_active_driver
    def _on_stop_heater_request(self, message=None):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        self.session.stop_heater(channel=int(params.get("channel", 0)))

    @require_active_driver
    def _on_get_temperature_request(self, message=None):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        channel = int(params.get("channel", 0))
        info = self.session.get_temperature(channel=channel)
        publish_message(
            json.dumps({"type": "temperature", "channel": channel, "info": info}),
            PORT_DROPBOT_TEMPERATURE_UPDATE,
        )

    # --- Frequency sweep & event streaming ---
    @run_in_background
    @require_active_driver
    @require_realtime_mode
    def _on_frequency_sweep_request(self, message):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        channels = params.get("channels")
        if not channels:
            logger.error("frequency_sweep missing channels")
            return
        results = self.session.frequency_sweep(
            channels,
            freqs=params.get("freqs"),
            voltage_v=float(params.get("voltage_v", 100)),
            settle_s=float(params.get("settle_s", 0.1)),
        )
        publish_message(
            json.dumps({
                "type": "frequency_sweep",
                "results": {str(f): c for f, c in results.items()},
            }),
            PORT_DROPBOT_SWEEP_RESULT,
        )

    @require_active_driver
    def _on_enable_streaming_request(self, message=None):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        mask = int(params.get("mask", SignalBoard.EVT_ALL))
        interval_ms = int(params.get("interval_ms", 1000))
        self.session.enable_streaming(mask=mask, interval_ms=interval_ms)
        logger.info(f"Event streaming enabled (mask=0x{mask:04X}, {interval_ms} ms)")

    @require_active_driver
    def _on_disable_streaming_request(self, message=None):
        if not self.connected:
            return
        self.session.disable_streaming()
        logger.info("Event streaming disabled")

    # --- Fans / buzzer / alarms / motor-board power ---
    @require_active_driver
    def _on_set_fan_request(self, message):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        on = self._msg_to_bool(params.get("on", params.get("value")), default=True)
        self.session.set_fan(on, board=params.get("board", "motor"))

    @require_active_driver
    def _on_set_buzzer_request(self, message):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        on = self._msg_to_bool(params.get("on", params.get("value")), default=True)
        self.session.set_buzzer(on)

    @require_active_driver
    def _on_clear_alarm_request(self, message):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        board, code = params.get("board"), params.get("code")
        if not board or not code:
            logger.error("clear_alarm requires board and code")
            return
        ok = self.session.clear_alarm(board, str(code))
        logger.info(f"Clear alarm {code} on {board}: {'ok' if ok else 'failed'}")

    @require_active_driver
    def _on_motor_board_power_request(self, message):
        if not self.connected:
            return
        params = self._msg_to_dict(message)
        on = self._msg_to_bool(params.get("on", params.get("value")), default=True)
        self.driver.motorBoardPowerCtrl(on)

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

        # sync connected driver to model
        self._sync_driver_to_model()

        arr = self.channel_states_arr
        if arr is not None and len(arr) > 0:
            if self.realtime_mode:
                self.driver.setElectrodeStates(arr)
            else:
                self.driver.setElectrodeStates(arr * 0)
        else:
            self.driver.setElectrodeStates(np.zeros(120, dtype=bool))

        self._send_device_status_update()

    def _send_device_status_update(self):
        # Prefer getTray() for chip state when motor board responds; else use positions
        chip_inserted = None
        try:
            tray_state = self.driver.getTray()
            if tray_state is not None:
                chip_inserted = bool(tray_state == 0)  # 0 = in (chip loaded)
        except Exception:
            pass
        if chip_inserted is None:
            tray_home, pogo_home = self._check_tray_and_pogo_home()
            chip_inserted = tray_home and pogo_home

        publish_message("", DROPBOT_CONNECTED)

        if  chip_inserted:
            publish_message("True", CHIP_INSERTED)
        else:
            publish_message("False", CHIP_INSERTED)

    def _check_tray_and_pogo_home(self):
        """
        Check tray and pogo home in one call to avoid double getMotorPositions().
        Returns (tray_home: bool, pogo_home: bool).
        """
        motor_pos = self.driver.getMotorPositions()
        if motor_pos is False:
            return False, False

        params = self.driver_params.get("motor_board") or {}
        tray_defaults = params.get("tray_defaults") or {}
        expected_tray_home = tray_defaults.get("in_pos")
        tray_pos = motor_pos.get("tray")
        tray_home = (
            expected_tray_home is not None and tray_pos == expected_tray_home
        )

        pogo_defaults = params.get("pogo_defaults")
        if pogo_defaults is None:
            return tray_home, False
        pogo_left = motor_pos.get("pogo_left", 0)
        pogo_right = motor_pos.get("pogo_right", 0)
        expected_pogo_home = pogo_defaults * 2
        pogo_home = (pogo_left + pogo_right) == expected_pogo_home

        return tray_home, pogo_home

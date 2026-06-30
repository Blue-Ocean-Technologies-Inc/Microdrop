from peripheral_device_controller_base.consts import connected_topic, disconnected_topic, searching_topic

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

DEVICE_NAME = "Heater"

# Heater controller hardware id (RP2040 / MicroPython, VID 2E8A, PID 0005).
HEATER_HWID = "VID:PID=2E8A:0005"
BOARD_BAUDRATE = 115200

# Heater channel targeted when a command payload omits one (mirrors the old UI
# fallback). The set of real channels is discovered on connect and published on
# HEATERS_AVAILABLE so a frontend can offer a selection dropdown.
DEFAULT_HEATER = "tec1"

# Markers the firmware wraps its `dump_config` JSON response in.
CONFIG_BEGIN = "<<<CONFIG_BEGIN>>>"
CONFIG_END = "<<<CONFIG_END>>>"
CONFIG_ERROR_PREFIX = "<<<CONFIG_ERROR"

# Topics published by this plugin (signals)
CONNECTED = connected_topic(DEVICE_NAME)
DISCONNECTED = disconnected_topic(DEVICE_NAME)
# JSON bool: True while scanning for the board, False once connected/stopped.
SEARCHING = searching_topic(DEVICE_NAME)
HEATERS_AVAILABLE = f"{DEVICE_NAME}/signals/heaters_available"
# Parsed §<FRAME>{json} telemetry packets (temperatures, PWM, board id, events).
TELEMETRY = f"{DEVICE_NAME}/signals/telemetry"

# Service Request Topics
START_DEVICE_MONITORING = f"{DEVICE_NAME}/requests/start_device_monitoring"
RETRY_CONNECTION = f"{DEVICE_NAME}/requests/retry_connection"
SEND_COMMAND = f"{DEVICE_NAME}/requests/send_command"
SET_TEMPERATURE = f"{DEVICE_NAME}/requests/set_temperature"
SET_PWM = f"{DEVICE_NAME}/requests/set_pwm"
SET_PID_MODE = f"{DEVICE_NAME}/requests/set_pid_mode"
SET_STREAM = f"{DEVICE_NAME}/requests/set_stream"
SET_FAN = f"{DEVICE_NAME}/requests/set_fan"
ALL_OFF = f"{DEVICE_NAME}/requests/all_off"

# Topics actor declared by plugin subscribes to. The listener-name key MUST match
# HeaterControllerBase.listener_name.
ACTOR_TOPIC_DICT = {
    "heater_controller_listener": [
        f"{DEVICE_NAME}/requests/#",
        CONNECTED,
        DISCONNECTED,
    ]}

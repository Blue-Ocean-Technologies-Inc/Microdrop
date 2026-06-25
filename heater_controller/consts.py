from peripheral_device_controller_base.consts import connected_topic, disconnected_topic

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

DEVICE_NAME = "Heater"

# Heater controller hardware id (RP2040 / MicroPython, VID 2E8A, PID 0005).
HEATER_HWID = "VID:PID=2E8A:0005"
BOARD_BAUDRATE = 115200

# Topics published by this plugin
CONNECTED = connected_topic(DEVICE_NAME)
DISCONNECTED = disconnected_topic(DEVICE_NAME)

# Service Request Topics
START_DEVICE_MONITORING = f"{DEVICE_NAME}/requests/start_device_monitoring"
RETRY_CONNECTION = f"{DEVICE_NAME}/requests/retry_connection"
SEND_COMMAND = f"{DEVICE_NAME}/requests/send_command"

# Topics actor declared by plugin subscribes to. The listener-name key MUST match
# HeaterControllerBase.listener_name.
ACTOR_TOPIC_DICT = {
    "heater_controller_listener": [
        f"{DEVICE_NAME}/requests/#",
        CONNECTED,
        DISCONNECTED,
    ]}

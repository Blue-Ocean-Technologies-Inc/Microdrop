# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")


PORT_DROPBOT_STATUS_UPDATE = "portable_dropbot/signals/board_status_update"
TOGGLE_DROPBOT_LOADING = "dropbot/requests/toggle_tray"
# Define topics for new controls
SET_CHIP_LOCK = "dropbot/requests/lock_chip"
SET_LIGHT_INTENSITY = "dropbot/requests/set_light_intensity"

SET_MOTOR_RELATIVE_MOVE = "dropbot/requests/motor_relative_move"
SET_MOTOR_ABSOLUTE_MOVE = "dropbot/requests/motor_absolute_move"
SET_MOTOR_HOME = "dropbot/requests/motor_home"
SET_TOGGLE_MOTOR = "dropbot/requests/toggle_motor"

# ---------------------------------------------------------------------------
# Session-API request topics (app -> driver). All live under the
# "dropbot/requests/#" wildcard already subscribed below, and are dispatched
# to ConnectionManager._on_<name>_request handlers by basic_listener_actor_routine.
# ---------------------------------------------------------------------------
# Diagnostics & detection
SELF_TEST = "dropbot/requests/self_test"
SHORT_CIRCUIT_SCAN = "dropbot/requests/short_circuit_scan"
DETECT_SHORTS = "dropbot/requests/detect_shorts"
CALIBRATE_CAPACITORS = "dropbot/requests/calibrate_capacitors"
MEASURE_CAPACITANCE = "dropbot/requests/measure_capacitance"

# Feedback-controlled actuation
RAMP_VOLTAGE = "dropbot/requests/ramp_voltage"
CALIBRATE_BASELINE = "dropbot/requests/calibrate_baseline"
DETECT_DROPS = "dropbot/requests/detect_drops"
ACTUATE_AND_VERIFY = "dropbot/requests/actuate_and_verify"

# Temperature control
SET_TEMPERATURE = "dropbot/requests/set_temperature"
STOP_HEATER = "dropbot/requests/stop_heater"
GET_TEMPERATURE = "dropbot/requests/get_temperature"

# Frequency sweep & event streaming
FREQUENCY_SWEEP = "dropbot/requests/frequency_sweep"
ENABLE_STREAMING = "dropbot/requests/enable_streaming"
DISABLE_STREAMING = "dropbot/requests/disable_streaming"

# Fans / buzzer / alarms / power
SET_FAN = "dropbot/requests/set_fan"
SET_BUZZER = "dropbot/requests/set_buzzer"
CLEAR_ALARM = "dropbot/requests/clear_alarm"
MOTOR_BOARD_POWER = "dropbot/requests/motor_board_power"

# ---------------------------------------------------------------------------
# Outbound result/signal topics (driver -> app). Published by the manager.
# ---------------------------------------------------------------------------
PORT_DROPBOT_DIAGNOSTICS_RESULT = "portable_dropbot/signals/diagnostics_result"
PORT_DROPBOT_TEMPERATURE_UPDATE = "portable_dropbot/signals/temperature_update"
PORT_DROPBOT_SWEEP_RESULT = "portable_dropbot/signals/sweep_result"
PORT_DROPBOT_DROPS_RESULT = "portable_dropbot/signals/drops_result"
PORT_DROPBOT_CAPACITANCE_RESULT = "portable_dropbot/signals/capacitance_result"

from peripheral_controller.consts import GO_HOME, SET_POSITION, MOVE_UP, MOVE_DOWN

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "dropbot/requests/#",
SET_TOGGLE_MOTOR, SET_MOTOR_HOME, SET_MOTOR_RELATIVE_MOVE, SET_MOTOR_ABSOLUTE_MOVE,
        GO_HOME, MOVE_UP, MOVE_DOWN, SET_POSITION
    ]}
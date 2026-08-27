# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Serial defaults for the Portable Dropbot boards. The driver's
#: connect() probes its own baud whitelist beyond this starting rate.
DEFAULT_BAUD_RATE = 115200

#: Channel-count fallback for request validation before the driver's
#: own board detection (120 or 200) has answered.
DEFAULT_NUM_CHANNELS = 200

#: HV actuation defaults (both Int end-to-end, like every device) and
#: UI setpoint bounds, carried over from the original portable pane
#: (which drove this same hardware).
DEFAULT_VOLTAGE = 100
DEFAULT_FREQUENCY = 10_000
VOLTAGE_BOUNDS = (30, 200)
FREQUENCY_BOUNDS = (50, 60_000)

#: Illumination LED brightness (%), applied on connect and from the
#: status pane's spinner. The firmware takes a raw 0-255 byte.
LIGHT_INTENSITY_BOUNDS = (0, 100)
DEFAULT_LIGHT_INTENSITY = 50
LIGHT_INTENSITY_RAW_MAX = 255

#: RGB indicator LED states the signal board knows.
RGB_LIGHT_STATES = ("off", "red", "green", "yellow")

#: The fluorescence LED's raw 16-bit brightness ceiling (the panel
#: exposes it as a %).
FLUORESCENCE_LED_RAW_MAX = 65_535

#: ML calibration runs at EXACTLY this V/F (hardware-validated by the
#: vendor's own calibration macro; anything else invalidates the fit).
CAL_VOLTAGE = 100
CAL_FREQUENCY = 10_000

#: Electrode-path capacitance gain (permille, EF-persisted); 692 is
#: the vendor's HW-benchmark default for the 10 pF/channel board.
ELECTRODE_GAIN_PERMILLE_BOUNDS = (0, 5000)
DEFAULT_ELECTRODE_GAIN_PERMILLE = 692

#: Multi-slope reference-cap provisioning: 3 = 10/100/470 pF board,
#: 5 = new board adding 1000/2200 pF.
CAL_CAPS_CHOICES = (3, 5)

#: Heater channels and target bounds, per the vendor UI's
#: Temp/Lighting tab.
TEMP_CHANNEL_MAX = 3
TEMP_TARGET_C_BOUNDS = (-50.0, 150.0)
TEMP_PID_GAIN_BOUNDS = (-1000.0, 1000.0)
TEMP_PID_PERIOD_MS_BOUNDS = (1, 60_000)

#: PMT gain is the MCP41010 wiper position (one byte).
PMT_GAIN_BOUNDS = (0, 255)
DEFAULT_PMT_GAIN = 128

#: The driver's fixed motor roster: name -> motor id.
MOTOR_IDS = {"tray": 0, "pmt": 1, "magnet": 2, "filter": 3,
             "pogo_left": 4, "pogo_right": 5}

#: Motor name -> the driver PARAMS friendly name whose EasyFlash blob
#: holds that motor's mechanical tuning struct.
MOTOR_PARAM_NAMES = {
    "tray": "tray_motor", "pmt": "pmt_motor", "magnet": "magnet_motor",
    "filter": "filter_motor", "pogo_left": "pogo_motor_left",
    "pogo_right": "pogo_motor_right",
}

#: The per-motor mechanical param struct, in WIRE ORDER (big-endian,
#: 6 floats then int32s). Older firmware stops at rspd (14 fields);
#: newer adds the accel/decel ramp factors (16). Reads accept either
#: length and writes send back exactly the fields that were read.
MOTOR_PARAM_FIELDS = (
    ("nl_pos", "f"), ("pl_pos", "f"), ("round_len", "f"),
    ("origin_offset", "f"), ("origin_area", "f"), ("step_len", "f"),
    ("motor_polarity", "i"), ("I_hold", "i"), ("I_run", "i"),
    ("subdiv", "i"), ("run_sgt", "i"), ("rst_sgt", "i"),
    ("bspd", "i"), ("rspd", "i"), ("acc_run", "i"), ("acc_rst", "i"),
)

#: Fluorescence filter wheel positions the hardware knows.
FILTER_POSITIONS = (0, 1, 2, 3, 4)

#: Seconds between monitor ticks: a port scan while disconnected, a
#: status poll (published to the panes) while connected.
MONITOR_INTERVAL_S = 2

#: Consecutive status polls with neither board answering before the
#: link is declared dead and scanning resumes. Without this a silent
#: board is polled forever — every poll a stack of command timeouts
#: that overruns the tick and floods the log — while the UI says
#: "Active".
STATUS_FAILURE_DISCONNECT_LIMIT = 3

# Shared hardware topics (same strings every device backend uses; the
# backend with a live proxy is the one that acts).
PORTABLE_DROPBOT_CONNECTED = "hardware/signals/connected"
PORTABLE_DROPBOT_DISCONNECTED = "hardware/signals/disconnected"
ELECTRODES_STATE_CHANGE = "hardware/requests/electrodes_state_change"
SET_REALTIME_MODE = "hardware/requests/set_realtime_mode"
REALTIME_MODE_UPDATED = "hardware/signals/realtime_mode_updated"

# Signals published by this plugin.
STATUS_UPDATED = "portable_dropbot/signals/status_updated"
#: Serial ports present on the machine that owns the hardware — the
#: frontend can be remote, so the backend enumerates and publishes.
PORTS_UPDATED = "portable_dropbot/signals/ports_updated"
MOTORS_UPDATED = "portable_dropbot/signals/motors_updated"
#: Calibration pane feedback: macro stage progress, gain/cal-caps
#: readbacks, ML-path state.
CALIBRATION_UPDATED = "portable_dropbot/signals/calibration_updated"
#: Temp pane feedback: per-channel readings and PID readbacks.
TEMP_UPDATED = "portable_dropbot/signals/temp_updated"
#: PMT pane feedback: power state, gain, acquire results.
PMT_UPDATED = "portable_dropbot/signals/pmt_updated"
#: Motor-params pane feedback: read-back field values, write/preset/
#: reboot outcomes.
MOTOR_PARAMS_UPDATED = "portable_dropbot/signals/motor_params_updated"
ALARM_RAISED = "portable_dropbot/signals/alarm"
ERROR_RAISED = "portable_dropbot/signals/error"

# Request topics handled by this plugin.
RETRY_CONNECTION = "portable_dropbot/requests/retry_connection"
#: Explicit user-chosen serial port (e.g. COM5) to connect on, from
#: the status pane's port picker; empty message = resume scanning.
CONNECT_TO_PORT = "portable_dropbot/requests/connect_to_port"
#: Ask the backend to publish its current port list (PORTS_UPDATED).
REFRESH_PORTS = "portable_dropbot/requests/refresh_ports"
#: User-requested disconnect; pauses the port scanner so the board
#: is not immediately re-acquired.
DISCONNECT = "portable_dropbot/requests/disconnect"
SET_VOLTAGE = "portable_dropbot/requests/set_voltage"
SET_FREQUENCY = "portable_dropbot/requests/set_frequency"
MOVE_TRAY = "portable_dropbot/requests/move_tray"
MOVE_MAGNET = "portable_dropbot/requests/move_magnet"
SET_FILTER = "portable_dropbot/requests/set_filter"
SET_POGO = "portable_dropbot/requests/set_pogo"
#: Chip lock IS the pogo pads pressing the chip; its own topic so
#: protocol steps and panes can say what they mean.
LOCK_CHIP = "portable_dropbot/requests/lock_chip"
SET_LIGHT_INTENSITY = "portable_dropbot/requests/set_light_intensity"
#: Illumination on/off without losing the % setpoint.
SET_LIGHT_ON = "portable_dropbot/requests/set_light_on"
SET_RGB_LIGHT = "portable_dropbot/requests/set_rgb_light"
#: Raw firmware-unit variants, mirroring the vendor UI's
#: Temp/Lighting tab (illumination 0-255, fluorescence 0-65535).
SET_ILLUMINATION_RAW = "portable_dropbot/requests/set_illumination_raw"
SET_FLUORESCENCE_LED_RAW = \
    "portable_dropbot/requests/set_fluorescence_led_raw"
# Calibration (see the calibration mixin service).
RUN_CAP_CALIBRATION = "portable_dropbot/requests/run_cap_calibration"
SET_ML_REALTIME = "portable_dropbot/requests/set_ml_realtime"
SET_ELECTRODE_GAIN = "portable_dropbot/requests/set_electrode_gain"
READ_ELECTRODE_GAIN = "portable_dropbot/requests/read_electrode_gain"
SET_CAL_CAPS = "portable_dropbot/requests/set_cal_caps"
READ_CAL_CAPS = "portable_dropbot/requests/read_cal_caps"
# Heater temperature control (per channel).
TEMP_SET_TARGET = "portable_dropbot/requests/temp_set_target"
TEMP_CONTROL = "portable_dropbot/requests/temp_control"
TEMP_READ_INFO = "portable_dropbot/requests/temp_read_info"
TEMP_READ_PID = "portable_dropbot/requests/temp_read_pid"
TEMP_SET_PID = "portable_dropbot/requests/temp_set_pid"
# PMT.
PMT_POWER = "portable_dropbot/requests/pmt_power"
PMT_SET_GAIN = "portable_dropbot/requests/pmt_set_gain"
PMT_ACQUIRE = "portable_dropbot/requests/pmt_acquire"
# Power system (advanced): fan and buzzer only.
SET_FAN = "portable_dropbot/requests/set_fan"
SET_BUZZER = "portable_dropbot/requests/set_buzzer"
# Motor mechanical params (advanced): RAM write, flash preset, and
# the reboot that makes flashed params take effect.
MOTOR_PARAMS_READ = "portable_dropbot/requests/motor_params_read"
MOTOR_PARAMS_WRITE = "portable_dropbot/requests/motor_params_write"
MOTOR_PARAMS_PRESET = "portable_dropbot/requests/motor_params_preset"
REBOOT_MOTOR_BOARD = "portable_dropbot/requests/reboot_motor_board"
HOME_ALL = "portable_dropbot/requests/home_all"
MOTOR_MOVE = "portable_dropbot/requests/motor_move"
MOTOR_SET_SPEED = "portable_dropbot/requests/motor_set_speed"
MOTOR_STOP = "portable_dropbot/requests/motor_stop"
MOTOR_HOME = "portable_dropbot/requests/motor_home"
REFRESH_MOTORS = "portable_dropbot/requests/refresh_motors"

# Topics the actor declared by this plugin subscribes to.
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        "portable_dropbot/requests/#",
        "hardware/requests/#",
        PORTABLE_DROPBOT_CONNECTED,
        PORTABLE_DROPBOT_DISCONNECTED,
    ]
}

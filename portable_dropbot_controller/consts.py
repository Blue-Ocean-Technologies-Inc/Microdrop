# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Serial defaults for the Portable Dropbot boards. The driver's
#: connect() probes its own baud whitelist beyond this starting rate.
DEFAULT_BAUD_RATE = 115200

#: Channel-count fallback for request validation before the driver's
#: own board detection (120 or 200) has answered.
DEFAULT_NUM_CHANNELS = 200

#: HV actuation defaults (both Int end-to-end, like every device).
DEFAULT_VOLTAGE = 100
DEFAULT_FREQUENCY = 10_000

#: Illumination LED brightness (%), applied on connect and from the
#: status pane's spinner.
LIGHT_INTENSITY_BOUNDS = (0, 100)
DEFAULT_LIGHT_INTENSITY = 50

#: The driver's fixed motor roster: name -> motor id.
MOTOR_IDS = {"tray": 0, "pmt": 1, "magnet": 2, "filter": 3,
             "pogo_left": 4, "pogo_right": 5}

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
MOTORS_UPDATED = "portable_dropbot/signals/motors_updated"
ALARM_RAISED = "portable_dropbot/signals/alarm"
ERROR_RAISED = "portable_dropbot/signals/error"

# Request topics handled by this plugin.
RETRY_CONNECTION = "portable_dropbot/requests/retry_connection"
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
HOME_ALL = "portable_dropbot/requests/home_all"
MOTOR_MOVE = "portable_dropbot/requests/motor_move"
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

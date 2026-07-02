from microdrop_style.colors import ERROR_COLOR, SUCCESS_COLOR, GREY

from heater_controller.consts import (  # noqa: F401 (re-export)
    DEVICE_NAME, START_DEVICE_MONITORING, DUMP_CONFIG, TELEMETRY,
)

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ").replace("Ui", "UI")
listener_name = f"{PKG}_listener"
# The plots dock pane taps telemetry through its own listener (re-exported from
# plots.consts for use inside the plots package).
plot_listener_name = f"{PKG}_plot_listener"

# Main listener subscribes to all heater signals (connected/disconnected,
# heaters_available, telemetry); the plot listener taps telemetry only.
ACTOR_TOPIC_DICT = {
    listener_name: [f"{DEVICE_NAME}/signals/#"],
    plot_listener_name: [TELEMETRY],
}

# Setpoint ranges (units shown in the spinbox suffix).
TEMPERATURE_MIN, TEMPERATURE_MAX, TEMPERATURE_DEFAULT = 0, 150, 40
PWM_MIN, PWM_MAX, PWM_DEFAULT = 0, 100, 0

# Status colors. The heater has no chip/"no device" sub-state, so connected maps
# straight to the green "connected" color (no yellow intermediate).
disconnected_color = GREY["lighter"]
connected_color = SUCCESS_COLOR
halted_color = ERROR_COLOR

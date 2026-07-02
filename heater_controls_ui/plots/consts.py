"""Constants + brand-derived palettes for the heater plots."""
from microdrop_style.colors import (
    INFO_COLOR, WARNING_COLOR, ERROR_COLOR, SUCCESS_COLOR,
    PRIMARY_SHADE, SECONDARY_SHADE, GREY, WHITE,
)
from heater_controls_ui.consts import PKG, plot_listener_name  # noqa: F401 (re-export)

# ``plot_listener_name`` (the distinct telemetry listener for this pane) is
# owned by heater_controls_ui.consts alongside ACTOR_TOPIC_DICT; re-exported
# here so the plots package can import it locally.

# The plot dock pane's identity.
PLOT_DOCK_PANE_ID = f"{PKG}.plot_dock_pane"
PLOT_DOCK_PANE_NAME = "Heater Plots"

# Rolling-window size and redraw cadence (mirrors the old heater UI: a smooth
# live view without unbounded memory growth).
MAX_PLOT_POINTS = 500
PLOT_UPDATE_INTERVAL_MS = 500

# Categorical palette for per-sensor temperature lines — brand colours ordered
# for high adjacent contrast, cycled when there are more sensors than colours.
SENSOR_PALETTE = (
    INFO_COLOR,             # blue
    WARNING_COLOR,          # orange
    PRIMARY_SHADE[600],     # green
    SECONDARY_SHADE[500],   # indigo
    PRIMARY_SHADE[300],     # light green
    SECONDARY_SHADE[800],   # dark blue
    WARNING_COLOR,          # (re-used with offset never matters — cycle guard)
    GREY["dark"],           # grey
)

# Per-heater colour, shared between a heater's PID-temperature line (temp axis,
# dashed) and its PWM line (pwm axis, solid) so the eye links the two. Echoes
# the old UI's blue/red TEC1/TEC2 using brand hues.
HEATER_PALETTE = (
    SECONDARY_SHADE[700],   # deep blue
    ERROR_COLOR,            # red
    WARNING_COLOR,          # orange
    SUCCESS_COLOR,          # green
)

# Theme backgrounds (dark bg matches the app's dark theme surface; light uses
# brand white). Text/grid come from GREY/WHITE at draw time.
DARK_PLOT_BG = "#2B2B2B"
LIGHT_PLOT_BG = WHITE

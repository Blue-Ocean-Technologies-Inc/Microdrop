"""Constants + brand-derived palettes for the heater plots."""
from microdrop_style.colors import (
    INFO_COLOR, WARNING_COLOR, ERROR_COLOR, SUCCESS_COLOR,
    PRIMARY_SHADE, SECONDARY_SHADE, GREY, WHITE,
)
from heater_controls_ui.consts import PKG

# The plot dock pane's identity.
PLOT_DOCK_PANE_ID = f"{PKG}.plot_dock_pane"
PLOT_DOCK_PANE_NAME = "Heater Plots"

# Rolling-window size and redraw cadence (mirrors the old heater UI: a smooth
# live view without unbounded memory growth).
MAX_PLOT_POINTS = 500
PLOT_UPDATE_INTERVAL_MS = 500

# Role prefixes namespacing the toggleable series keys (a heater's PID and PWM
# series share the heater name, so bare names would collide in hidden_series).
SENSOR_SERIES_PREFIX = "sensor:"
PID_SERIES_PREFIX = "pid:"
PWM_SERIES_PREFIX = "pwm:"

# Legend entries for hidden series stay visible but dimmed to this alpha.
HIDDEN_LEGEND_ENTRY_ALPHA = 0.25

# Pause / Stop plot buttons (checkable, icon-font glyphs).
PAUSE_PLOT_TOOLTIP = ("Pause the plot. Data keeps arriving in the background; "
                      "resume to continue (a gap marks the pause).")
STOP_PLOT_TOOLTIP = ("Stop plotting entirely and discard the history. "
                     "Use this if the plot slows the application down.")

# Categorical palette for per-sensor temperature lines — brand colours ordered
# for high adjacent contrast, cycled when there are more sensors than colours.
SENSOR_PALETTE = (
    INFO_COLOR,             # blue
    WARNING_COLOR,          # orange
    PRIMARY_SHADE[600],     # green
    SECONDARY_SHADE[500],   # indigo
    PRIMARY_SHADE[300],     # light green
    SECONDARY_SHADE[800],   # dark blue
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

"""Package-level constants for the pluggable protocol tree.

Follows the MicroDrop convention: PKG derived from __name__, topic constants
defined here, ACTOR_TOPIC_DICT aggregating the listener-->topic map."""

import os

from device_viewer.consts import PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE, DEVICE_VIEWER_GEOMETRY_CHANGED, \
    DEVICE_VIEWER_STATE_CHANGED, DEVICE_VIEWER_MEDIA_CAPTURED, CALIBRATION_DATA, STEP_PARAMS_COMMIT

from dropbot_controller.consts import CAPACITANCE_UPDATED, REALTIME_MODE_UPDATED

from electrode_controller.consts import ELECTRODES_STATE_CHANGE, ELECTRODES_STATE_APPLIED

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

# Envisage extension point id (registered in plugin.py)
PROTOCOL_COLUMNS = f"{PKG}.protocol_columns"

# Settings-dialog category id for the tree's Protocol Settings tab.
# Other plugins anchoring panes to this tab import the constant (the
# sanctioned constants-only cross-import), not the category object.
PROTOCOL_TREE_PREFERENCES_TAB_ID = "microdrop.protocol_tree.preferences"

# Clipboard MIME type for copy/cut/paste of protocol rows
PROTOCOL_ROWS_MIME = "application/x-microdrop-rows+json"

# QFileDialog name filter shared by save / load / import dialogs
PROTOCOL_FILE_DIALOG_FILTER = "Protocol JSON (*.json)"

# ProtocolPreferences defaults (ported from protocol_grid with the
# preferences model, #419 / PPT-14.1).
DEFAULT_CAMERA_PREWARM_SECONDS = 3.0
DEFAULT_REALTIME_SETTLING_SECONDS = 1.0
DEFAULT_LOGS_SETTLING_SECONDS = 3.0
# Slider bounds for those preference fields.
CAMERA_PREWARM_MIN_S = 0.2
CAMERA_PREWARM_MAX_S = 15.0
SETTLING_TIME_MIN_S = 0.5
SETTLING_TIME_MAX_S = 15.0

# Bounds for the per-column acknowledgement-wait times configured in the
# Protocol Settings tab (#427). 0 = don't wait for the ack.
ACK_TIMEOUT_MIN_S = 0.0
ACK_TIMEOUT_MAX_S = 120.0
# Stored sentinel for "wait forever" (shown as ∞ in the grid). Finite
# because the preference dict round-trips through literal_eval, which
# rejects float("inf"); consumers translate it to an unbounded wait.
ACK_WAIT_FOREVER = -1.0

# Fields whose change triggers an auto-recalc of Route Reps Dur while the
# row is in Route-Reps-controlled mode (see ProtocolTreePane.
# _reconcile_repeat_duration_for_row).
REPEAT_DURATION_RECALC_TRIGGERS = frozenset({
    "route_repetitions", "duration_s", "trail_length", "trail_overlay",
    "routes", "soft_start", "soft_end", "linear_repeats",
})

# Step columns mirrored into the DV sidebar route executor (the tree side
# of the ProtocolTreeDisplayMessage.execution_params contract). A change to
# any of these on the selected step republishes display state so the DV
# sidebar reloads + rebaselines - protocol values supersede the sidebar.
DV_EXECUTION_PARAM_COL_IDS = frozenset({
    "duration_s", "route_repetitions", "repeat_duration", "trail_length",
    "trail_overlay", "soft_start", "soft_end", "linear_repeats",
})

# protocol_metadata / executor-scratch key carrying the per-device
# electrode-id -> channel map (written by the DV sync controller, read
# by phase publishers).
ELECTRODE_TO_CHANNEL_KEY = "electrode_to_channel"

# Persistence schema version
PERSISTENCE_SCHEMA_VERSION = 1

# Topic constants (no executor topics yet — added in PPT-2)
# Reserved namespace for future use:
PROTOCOL_TOPIC_PREFIX = "microdrop/protocol_tree"

# PPT-10.2: tree -> DV slim display message
PROTOCOL_TREE_DISPLAY_STATE = "ui/protocol_tree_display_state"

SYNC_LISTENER_NAME = "protocol_tree_dv_sync_listener"
EXECUTOR_LISTENER_NAME = "pluggable_protocol_tree_executor_listener"

ACTOR_TOPIC_DICT = {
    SYNC_LISTENER_NAME: [
        DEVICE_VIEWER_STATE_CHANGED,
        DEVICE_VIEWER_GEOMETRY_CHANGED,
        PROTOCOL_RUNNING,
        REALTIME_MODE_UPDATED,
        STEP_PARAMS_COMMIT,
    ]
}

LOGGING_LISTENER_NAME = "protocol_tree_logging_listener"
LOGGING_ACTOR_TOPIC_DICT = {
    LOGGING_LISTENER_NAME: [
        CAPACITANCE_UPDATED,
        ELECTRODES_STATE_CHANGE,
        DEVICE_VIEWER_MEDIA_CAPTURED,
        CALIBRATION_DATA,
    ]
}

# Envisage extension point — plugins contribute IQuickAction instances
# (see interfaces/i_quick_action.py) that render as buttons on the
# pluggable tree's quick-actions toolbar. Tree plugin ships zero
# builtins; all contributions come from sibling plugins.
PROTOCOL_QUICK_ACTIONS = f"{PKG}.protocol_quick_actions"


"""Package-level constants for the pluggable protocol tree.

Follows the MicroDrop convention: PKG derived from __name__, topic constants
defined here, ACTOR_TOPIC_DICT aggregating the listener-->topic map."""

import os

from device_viewer.consts import PROTOCOL_RUNNING, PROTOCOL_GRID_DISPLAY_STATE, DEVICE_VIEWER_GEOMETRY_CHANGED, \
    DEVICE_VIEWER_STATE_CHANGED, DEVICE_VIEWER_MEDIA_CAPTURED, CALIBRATION_DATA

from dropbot_controller.consts import CAPACITANCE_UPDATED, REALTIME_MODE_UPDATED

from electrode_controller.consts import ELECTRODES_STATE_CHANGE, ELECTRODES_STATE_APPLIED

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

# Envisage extension point id (registered in plugin.py)
PROTOCOL_COLUMNS = f"{PKG}.protocol_columns"

# Clipboard MIME type for copy/cut/paste of protocol rows
PROTOCOL_ROWS_MIME = "application/x-microdrop-rows+json"

# ProtocolPreferences defaults (relocated from protocol_grid with the
# preferences model, #419 / PPT-14.1).
DEFAULT_CAMERA_PREWARM_SECONDS = 3.0
DEFAULT_REALTIME_SETTLING_SECONDS = 1.0
DEFAULT_LOGS_SETTLING_SECONDS = 3.0

# Persistence schema version
PERSISTENCE_SCHEMA_VERSION = 1

# Topic constants (no executor topics yet — added in PPT-2)
# Reserved namespace for future use:
PROTOCOL_TOPIC_PREFIX = "microdrop/protocol_tree"

# PPT-10.2: tree -> DV slim display message
PROTOCOL_TREE_DISPLAY_STATE = "ui/protocol_tree_display_state"

SYNC_LISTENER_NAME = "protocol_tree_dv_sync_listener"

ACTOR_TOPIC_DICT = {
    SYNC_LISTENER_NAME: [
        DEVICE_VIEWER_STATE_CHANGED,
        DEVICE_VIEWER_GEOMETRY_CHANGED,
        PROTOCOL_RUNNING,
        REALTIME_MODE_UPDATED
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


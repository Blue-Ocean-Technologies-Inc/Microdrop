from pathlib import Path

from device_viewer.models.media import RecordingStatePublisher, RecordingStateModel
from dropbot_controller.consts import (
    CHIP_INSERTED,
    CAPACITANCE_UPDATED,
    DISABLED_CHANNELS_CHANGED,
    DROPLETS_DETECTED,
    REALTIME_MODE_UPDATED,
    DROPBOT_DISCONNECTED,
    DROPBOT_CONNECTED,
    SHORTS_DETECTED, HALTED,
)

# ---------------------------------------------------------------------------
# Package identity
# ---------------------------------------------------------------------------
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")
listener_name = f"{PKG}_listener"

# ---------------------------------------------------------------------------
# Pub/sub topics
# ---------------------------------------------------------------------------
# Device-viewer topics — canonical home (re-exported by protocol_grid.consts for back-compat).
# Once protocol_grid is deleted in PPT-9, these stay; the re-exports go away.
DEVICE_VIEWER_STATE_CHANGED    = "ui/device_viewer/state_changed"
DEVICE_VIEWER_SCREEN_CAPTURE   = "ui/device_viewer/screen_capture"
DEVICE_VIEWER_SCREEN_RECORDING = "ui/device_viewer/screen_recording"
DEVICE_VIEWER_CAMERA_ACTIVE    = "ui/device_viewer/camera_active"
DEVICE_VIEWER_MEDIA_CAPTURED   = "ui/device_viewer/camera/media_captured"
DEVICE_VIEWER_RECORDING_STATE  = "ui/device_viewer/recording_state"
DEVICE_VIEWER_GEOMETRY_CHANGED = "ui/device_viewer/geometry_changed"
# Sidebar route preview/playback is running (payload "True"/"False"). Published
# by device_viewer's RouteExecutionService. Canonical home moved here from the
# deleted protocol_grid.consts in PPT-9 (#371).
ROUTES_EXECUTING               = "ui/device_viewer/routes_executing"
CALIBRATION_DATA               = "ui/calibration_data"

# Sidebar route-executor execution params -> the selected protocol step.
# Published by the DV commit button; consumed by the active protocol widget
# (pluggable_protocol_tree sync controller; protocol_grid keeps its own
# duplicated literal until PPT-9 deletes it). Schema:
# device_viewer/models/step_params_commit.py.
STEP_PARAMS_COMMIT             = "ui/device_viewer/step_params_commit"

# Live gamepad button-capture (remap) request: payload is the action name being
# rebound (e.g. "split"). Published by the Gamepad preferences pane, relayed by
# the device-viewer listener to the live interaction service. Dispatches to
# _on_gamepad_capture_request_triggered (topic.split("/")[-1] == unique segment).
GAMEPAD_CAPTURE_REQUEST        = "ui/device_viewer/gamepad_capture_request"
# Manual gamepad reconnect request (payload unused). Lets the user re-attempt
# controller acquisition from the UI after an unplug/replug. Dispatches to
# _on_gamepad_reconnect_request_triggered.
GAMEPAD_RECONNECT_REQUEST      = "ui/device_viewer/gamepad_reconnect_request"

# Shared topics used by device_viewer actor subscriptions. Defined here as literals (rather than
# imported from protocol_grid.consts) to avoid the circular import that would otherwise form
# now that protocol_grid.consts re-exports the device_viewer topics above. Duplicated as literals
# in protocol_grid.consts; safe to consolidate once PPT-9 deletes protocol_grid.
PROTOCOL_GRID_DISPLAY_STATE    = "ui/protocol_grid/display_state"
PROTOCOL_RUNNING               = "microdrop/protocol_running"
# Literal here (matching PROTOCOL_TREE_DISPLAY_STATE below) to avoid importing
# microdrop_application.consts. Canonical home is microdrop_application.consts;
# value must stay in sync. Keeps the viewer editable mid-run in Advanced Mode (#434).
ADVANCED_MODE_CHANGE           = "microdrop/advanced_mode_change"
# Literal here to avoid circular import: pluggable_protocol_tree.consts imports from this module.
# NB: last segment must be unique vs PROTOCOL_GRID_DISPLAY_STATE — the dramatiq listener base
# dispatches by topic.split("/")[-1], so two topics ending in "display_state" collide on the
# same handler. Underscore-joined keeps dispatch routed to _on_protocol_tree_display_state_triggered.
PROTOCOL_TREE_DISPLAY_STATE    = "ui/protocol_tree_display_state"

# Topics the plugin's actor subscribes to.
ACTOR_TOPIC_DICT = {
    listener_name: [
        CHIP_INSERTED,
        REALTIME_MODE_UPDATED,
        PROTOCOL_GRID_DISPLAY_STATE,
        CAPACITANCE_UPDATED,
        DEVICE_VIEWER_SCREEN_CAPTURE,
        DEVICE_VIEWER_CAMERA_ACTIVE,
        DEVICE_VIEWER_SCREEN_RECORDING,
        DROPLETS_DETECTED,
        PROTOCOL_RUNNING,
        ADVANCED_MODE_CHANGE,
        DROPBOT_DISCONNECTED,
        DROPBOT_CONNECTED,
        DISABLED_CHANNELS_CHANGED,
        HALTED,
        PROTOCOL_TREE_DISPLAY_STATE,
        GAMEPAD_CAPTURE_REQUEST,
        GAMEPAD_RECONNECT_REQUEST,
        # Note: DEVICE_VIEWER_GEOMETRY_CHANGED is published BY the DV;
        # the DV does not consume it. The pluggable_protocol_tree
        # controller subscribes via SYNC_ACTOR_TOPIC_DICT.
    ]
}

# ---------------------------------------------------------------------------
# Publishers
# ---------------------------------------------------------------------------
device_viewer_recording_state_publisher = RecordingStatePublisher(topic=DEVICE_VIEWER_RECORDING_STATE)

# ---------------------------------------------------------------------------
# app_globals keys (stored in APP_GLOBALS_REDIS_HASH via the redis client)
# ---------------------------------------------------------------------------
CHANNEL_AREAS_KEY = "channel_electrode_areas_scaled_map" # channel areas
FILLER_CAPACITANCE_KEY = "filler_capacitance_over_area" # filler calibration
LIQUID_CAPACITANCE_KEY = "liquid_capacitance_over_area" # liquid calibration
DEVICE_SVG_PATH_KEY = "microdrop.device_svg.path" # the active svg file path
MEDIA_CAPTURES_KEY = "media_captures" # serialised camera captures for the active run.
DEVICE_VIEWER_RECORDING_ACTIVE_KEY = "device_viewer.recording_active" # live video-recording state

# Mirrors the live recording state to app_globals (see DEVICE_VIEWER_RECORDING_ACTIVE_KEY).
recording_state_model = RecordingStateModel(globals_key=DEVICE_VIEWER_RECORDING_ACTIVE_KEY)

APP_GLOBALS_KEYS = [CHANNEL_AREAS_KEY, FILLER_CAPACITANCE_KEY,
                    LIQUID_CAPACITANCE_KEY, DEVICE_SVG_PATH_KEY]

# ---------------------------------------------------------------------------
# Capture file layout (under the experiment directory). Other plugins may
# import these to LOCATE captures (e.g. the fluorescence image viewer);
# only the device viewer writes them.
# ---------------------------------------------------------------------------
CAPTURES_DIR_NAME = "captures"
RECORDINGS_DIR_NAME = "recordings"
# Unprocessed (16-bit) sensor frames from provider feeds, saved alongside
# every display capture under captures/.
RAW_CAPTURES_SUBDIR = "16bit_raw"

# ---------------------------------------------------------------------------
# GUI configuration
# ---------------------------------------------------------------------------
DEVICE_VIEWER_SIDEBAR_WIDTH = 320
ALPHA_VIEW_MIN_HEIGHT = 180
LAYERS_VIEW_MIN_HEIGHT = 250

# Default electrode channel count; configurable in Device Viewer preferences.
NUMBER_OF_CHANNELS = 120

# device view zoom sensitivity
ZOOM_SENSITIVITY = 5
# device view margin when auto fit
AUTO_FIT_MARGIN_SCALE = 95

# ---------------------------------------------------------------------------
# Gamepad defaults (configurable in Device Viewer preferences). Env vars of the
# form MICRODROP_GAMEPAD_* still override the stored preference at runtime.
# Button indices are for the common NES/SNES-style USB pad:
#   X=0, A=1, B=2, Y=3, L=4, R=5, Select=8, Start=9
# ---------------------------------------------------------------------------
GAMEPAD_BTN_CLEAR = 1      # A      -> clear all electrodes
GAMEPAD_BTN_FIND = 8       # Select -> find liquid
GAMEPAD_BTN_SPLIT = 2      # B hold -> split
GAMEPAD_BTN_ADD = 3        # Y hold -> add electrode
GAMEPAD_BTN_REMOVE = 0     # X hold -> remove electrode
GAMEPAD_BTN_REALTIME = 9   # Start  -> toggle realtime mode

GAMEPAD_DEBOUNCE_MOVE_SPLIT_S = 0.7   # D-pad move / split step debounce
GAMEPAD_DEBOUNCE_ADD_REMOVE_S = 0.3   # D-pad add / remove debounce
GAMEPAD_DEBOUNCE_FIND_S = 2.0         # find-liquid button debounce
GAMEPAD_DEBOUNCE_REALTIME_S = 0.4     # realtime-toggle button debounce
GAMEPAD_AXIS_THRESHOLD = 0.6          # analog-stick-as-D-pad activation threshold

# Poll cadence: ~100 Hz only while a controller is attached; with none,
# a slow tick suffices to catch JOYDEVICEADDED hot-plug events instead
# of waking the GUI thread 100x a second for nothing.
GAMEPAD_POLL_INTERVAL_MS = 10
GAMEPAD_IDLE_POLL_INTERVAL_MS = 500

# ---------------------------------------------------------------------------
# Resources & UI text
# ---------------------------------------------------------------------------
# main view device layout
MASTER_SVG_FILE = Path(__file__).parent / "resources" / "devices" / "90_pin_array.svg"
PIN_MAP_SVG_FILE = Path(__file__).parent / "resources" / "devices" / "pin_map.svg"

device_modified_tag = " (modified)"

# statusbar messages
camera_place_status_message_text = "Select 4 points on image"
camera_edit_status_message_text = "Drag vertices to align with device outline"

# Extension point: extra camera sources for the device-viewer camera panel.
# Contributions are zero-arg factories returning a provider object:
#   provider.list_sources() -> [(label, key)]      # dropdown entries
#   provider.open(key)      -> feed                # QObject with:
#       feed.error: Signal(str)                    #   fatal feed errors
#       feed.start() / feed.stop()                 #   lifecycle
#       feed.frame: Signal(QImage)                 #   optional preview frames
#       feed.streaming: Signal(bool)               #   optional preview state
#       feed.create_controls(parent) -> QWidget|None   # optional settings row
#       feed.raw_frame() -> QImage|None                # optional: unprocessed
#                                                      #   (e.g. 16-bit) frame,
#                                                      #   THE saved capture
# The feed owns its preview state: the device viewer shows its video layer
# only while feed.streaming reports True (e.g. the fluorescence pane's
# "Device View Stream" checkbox) — captures save the feed's raw frame
# directly either way.
CAMERA_SOURCES = "device_viewer.camera_sources"

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from pathlib import Path

from device_viewer.models.media import (
    MediaCaptureEventModel,
    RecordingStateModel,
    RecordingStatePublisher,
)
from dropbot_controller.consts import (
    CAPACITANCE_UPDATED,
    CHIP_INSERTED,
    DISABLED_CHANNELS_CHANGED,
    DROPBOT_CONNECTED,
    DROPBOT_DISCONNECTED,
    DROPLETS_DETECTED,
    HALTED,
    REALTIME_MODE_UPDATED,
)

# ---------------------------------------------------------------------------
# Package identity
# ---------------------------------------------------------------------------
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")
listener_name = f"{PKG}_listener"

# ---------------------------------------------------------------------------
# Pub/sub topics
# ---------------------------------------------------------------------------
# Device-viewer topics — canonical home (re-exported by protocol_grid.consts
# for back-compat). Once protocol_grid is deleted in PPT-9, these stay; the
# re-exports go away.
DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"
DEVICE_VIEWER_SCREEN_CAPTURE = "ui/device_viewer/screen_capture"
DEVICE_VIEWER_SCREEN_RECORDING = "ui/device_viewer/screen_recording"
DEVICE_VIEWER_CAMERA_ACTIVE = "ui/device_viewer/camera_active"
DEVICE_VIEWER_MEDIA_CAPTURED = "ui/device_viewer/camera/media_captured"
DEVICE_VIEWER_RECORDING_STATE = "ui/device_viewer/recording_state"
DEVICE_VIEWER_GEOMETRY_CHANGED = "ui/device_viewer/geometry_changed"
# Sidebar route preview/playback is running (payload "True"/"False"). Published
# by device_viewer's RouteExecutionService. Canonical home moved here from the
# deleted protocol_grid.consts in PPT-9 (#371).
ROUTES_EXECUTING = "ui/device_viewer/routes_executing"
CALIBRATION_DATA = "ui/calibration_data"

# Idle phase-navigation mode (#493): opt-in checkbox synced between the DV
# sidebar and the protocol tree. Payload "True"/"False". Published by
# whichever UI the user toggled; both subscribe (applying an equal value is
# a trait no-op, so echoes are harmless).
PHASE_NAVIGATION_MODE = "ui/phase_navigation_mode"
# Tree -> DV: navigate while idle-stepping. JSON payload:
# {"action": "prev" | "next" | "goto", "index": <int, goto only>}.
PHASE_NAVIGATION_REQUEST = "ui/device_viewer/phase_navigation_request"
# DV -> tree: current idle-nav position. JSON payload:
# {"phase_index": <0-based int>, "phase_total": <int>}; total 0 = no plan.
PHASE_NAVIGATION_STATE = "ui/device_viewer/phase_navigation_state"

# Sidebar route-executor execution params -> the selected protocol step.
# Published by the DV commit button; consumed by the active protocol widget
# (pluggable_protocol_tree sync controller; protocol_grid keeps its own
# duplicated literal until PPT-9 deletes it). Schema:
# device_viewer/models/step_params_commit.py.
STEP_PARAMS_COMMIT = "ui/device_viewer/step_params_commit"

# Live gamepad button-capture (remap) request: payload is the action name being
# rebound (e.g. "split"). Published by the Gamepad preferences pane, relayed by
# the device-viewer listener to the live interaction service. Dispatches to
# _on_gamepad_capture_request_triggered (topic.split("/")[-1] == unique segment).
GAMEPAD_CAPTURE_REQUEST = "ui/device_viewer/gamepad_capture_request"
# Manual gamepad reconnect request (payload unused). Lets the user re-attempt
# controller acquisition from the UI after an unplug/replug. Dispatches to
# _on_gamepad_reconnect_request_triggered.
GAMEPAD_RECONNECT_REQUEST = "ui/device_viewer/gamepad_reconnect_request"
# Ask the Device viewer to load an SVG. Lets other plugins (e.g. the legacy
# protocol import) switch devices without reaching into this one.
DEVICE_VIEWER_LOAD_SVG_REQUEST = "ui/device_viewer/load_svg_request"

# Shared topics used by device_viewer actor subscriptions. Defined here as
# literals (rather than imported from protocol_grid.consts) to avoid the
# circular import that would otherwise form now that protocol_grid.consts
# re-exports the device_viewer topics above. Duplicated as literals in
# protocol_grid.consts; safe to consolidate once PPT-9 deletes protocol_grid.
PROTOCOL_GRID_DISPLAY_STATE = "ui/protocol_grid/display_state"
PROTOCOL_RUNNING = "microdrop/protocol_running"
# Literal here (matching PROTOCOL_TREE_DISPLAY_STATE below) to avoid importing
# microdrop_application.consts. Canonical home is microdrop_application.consts;
# value must stay in sync. Keeps the viewer editable mid-run in Advanced Mode (#434).
ADVANCED_MODE_CHANGE = "microdrop/advanced_mode_change"
# Literal here to avoid circular import: pluggable_protocol_tree.consts
# imports from this module. NB: last segment must be unique vs
# PROTOCOL_GRID_DISPLAY_STATE — the dramatiq listener base dispatches by
# topic.split("/")[-1], so two topics ending in "display_state" collide on
# the same handler. Underscore-joined keeps dispatch routed to
# _on_protocol_tree_display_state_triggered.
PROTOCOL_TREE_DISPLAY_STATE = "ui/protocol_tree_display_state"

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
        DEVICE_VIEWER_LOAD_SVG_REQUEST,
        PHASE_NAVIGATION_MODE,
        PHASE_NAVIGATION_REQUEST,
        # Note: DEVICE_VIEWER_GEOMETRY_CHANGED is published BY the DV;
        # the DV does not consume it. The pluggable_protocol_tree
        # controller subscribes via SYNC_ACTOR_TOPIC_DICT.
    ]
}

# ---------------------------------------------------------------------------
# Publishers
# ---------------------------------------------------------------------------
device_viewer_recording_state_publisher = RecordingStatePublisher(
    topic=DEVICE_VIEWER_RECORDING_STATE
)

# ---------------------------------------------------------------------------
# app_globals keys (stored in APP_GLOBALS_REDIS_HASH via the redis client)
# ---------------------------------------------------------------------------
CHANNEL_AREAS_KEY = "channel_electrode_areas_scaled_map"  # channel areas
FILLER_CAPACITANCE_KEY = "filler_capacitance_over_area"  # filler calibration
LIQUID_CAPACITANCE_KEY = "liquid_capacitance_over_area"  # liquid calibration
DEVICE_SVG_PATH_KEY = "microdrop.device_svg.path"  # the active svg file path
DEVICE_REPO_DIR_KEY = "microdrop.device_repo.dir"  # the user device-SVG repo directory
MEDIA_CAPTURES_KEY = "media_captures"  # serialised camera captures for the active run.
DEVICE_VIEWER_RECORDING_ACTIVE_KEY = "device_viewer.recording_active"  # recording state
ZONES_KEY = "microdrop.device.zones"  # JSON snapshot of zone types + regions

# Mirrors the live recording state to app_globals (see
# DEVICE_VIEWER_RECORDING_ACTIVE_KEY).
recording_state_model = RecordingStateModel(
    globals_key=DEVICE_VIEWER_RECORDING_ACTIVE_KEY
)

# Fires with the saved file's path when a capture finishes writing — the
# event-driven alternative to polling the captures folder (e.g. the
# fluorescence image viewer refreshes on it).
media_capture_event_model = MediaCaptureEventModel()

APP_GLOBALS_KEYS = [
    CHANNEL_AREAS_KEY,
    FILLER_CAPACITANCE_KEY,
    LIQUID_CAPACITANCE_KEY,
    DEVICE_SVG_PATH_KEY,
    DEVICE_REPO_DIR_KEY,
    ZONES_KEY,
]

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
ZONE_TYPES_VIEW_MIN_HEIGHT = 200
ZONE_REGIONS_VIEW_MIN_HEIGHT = 200

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
GAMEPAD_BTN_CLEAR = 1  # A      -> clear all electrodes
GAMEPAD_BTN_FIND = 8  # Select -> find liquid
GAMEPAD_BTN_SPLIT = 2  # B hold -> split
GAMEPAD_BTN_ADD = 3  # Y hold -> add electrode
GAMEPAD_BTN_REMOVE = 0  # X hold -> remove electrode
GAMEPAD_BTN_REALTIME = 9  # Start  -> toggle realtime mode

GAMEPAD_DEBOUNCE_MOVE_SPLIT_S = 0.7  # D-pad move / split step debounce
GAMEPAD_DEBOUNCE_ADD_REMOVE_S = 0.3  # D-pad add / remove debounce
GAMEPAD_DEBOUNCE_FIND_S = 2.0  # find-liquid button debounce
GAMEPAD_DEBOUNCE_REALTIME_S = 0.4  # realtime-toggle button debounce
GAMEPAD_AXIS_THRESHOLD = 0.6  # analog-stick-as-D-pad activation threshold

# Poll cadence: ~100 Hz only while a controller is attached; with none,
# a slow tick suffices to catch JOYDEVICEADDED hot-plug events instead
# of waking the GUI thread 100x a second for nothing.
GAMEPAD_POLL_INTERVAL_MS = 10
GAMEPAD_IDLE_POLL_INTERVAL_MS = 500

# Sidecar written next to every recording by NativeVideoRecorder: the video
# item's alignment geometry, letting viewers reproduce the device-aligned
# (perspective-warped) view of the raw camera file on demand.
RECORDING_TRANSFORM_SIDECAR_SUFFIX = ".transform.json"

# ---------------------------------------------------------------------------
# Video recording preferences (camera preferences node). The recorder is
# rebuilt from these at every recording start, so changes apply live.
# ---------------------------------------------------------------------------
RECORDER_BACKEND_QT = "Qt MediaRecorder (hardware)"
RECORDER_BACKEND_FFMPEG = "FFmpeg process"

# Qt recorder container choices (drive both the QMediaFormat and the
# recording file extension).
QT_RECORDER_FORMAT_MP4 = "MP4"
QT_RECORDER_FORMAT_MKV = "MKV"

# FFmpeg-process recorder encoding choices. fps, resolution and pixel
# format are always taken from the camera, never from preferences.
FFMPEG_CONTAINERS = ("mkv", "mp4")
FFMPEG_VIDEO_CODECS = ("libx264", "libx265")
FFMPEG_PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)
FFMPEG_DEFAULT_CRF = 17

#: Qt/MKV recording quality tiers, easiest first: Auto is the recommended
#: rate for the class (same as Medium — the sweet spot of the commonly
#: recommended H.264 delivery bitrates), Low..Ultra span that range.
RECORDING_BITRATE_TIERS = ("Auto", "Low", "Medium", "High", "Ultra")

#: Resolution class label -> (CameraPreferences trait, {tier: Mbps}).
RECORDING_BITRATE_CLASSES = {
    "1080p @ 30 fps": (
        "qt_bitrate_1080p30_tier",
        {"Auto": 4.5, "Low": 3, "Medium": 4.5, "High": 6, "Ultra": 8},
    ),
    "1080p @ 60 fps": (
        "qt_bitrate_1080p60_tier",
        {"Auto": 6, "Low": 4.5, "Medium": 6, "High": 7.5, "Ultra": 9},
    ),
    "4K @ 24/30 fps": (
        "qt_bitrate_4k30_tier",
        {"Auto": 20, "Low": 15, "Medium": 20, "High": 25, "Ultra": 30},
    ),
    "4K @ 60 fps": (
        "qt_bitrate_4k60_tier",
        {"Auto": 45, "Low": 35, "Medium": 45, "High": 55, "Ultra": 70},
    ),
}
# Class-matching thresholds for the ACTUAL camera format at record time.
RECORDING_4K_MIN_HEIGHT = 1600  # frames at least this tall use the 4K classes
RECORDING_60FPS_MIN_FPS = 45  # at least this fps uses the 60 fps classes

# ---------------------------------------------------------------------------
# Camera preview
# ---------------------------------------------------------------------------
# Ceiling for frames forwarded to the device view's video item. Every frame
# composited under the electrodes is a full-scene repaint, and the preview
# doesn't need camera rate to be useful — recordings are unaffected (the
# recorder taps the capture session's own sink at full rate).
CAMERA_PREVIEW_MAX_FPS = 20

# ---------------------------------------------------------------------------
# Camera-alignment dialog (endpoint / outline panes)
# ---------------------------------------------------------------------------
#: QuadOverlay defaults. Colors are '#rrggbb' hex strings — the same
#: format the alignment preferences persist.
ALIGNMENT_QUAD_COLOR_HEX = "#ffa000"
ALIGNMENT_HANDLE_COLOR_HEX = "#ff6400"
ALIGNMENT_HANDLE_RING_COLOR_HEX = "#ffffff"
ALIGNMENT_HANDLE_RADIUS_PX = 8
ALIGNMENT_FRAME_WIDTH_PX = 3
ALIGNMENT_SNAP_RADIUS_PX = 100

#: The view-all-snappable-corners markers (toggled per pane): dot
#: size is in VIEW pixels (cosmetic pen — constant at any zoom).
ALIGNMENT_SNAP_MARKER_COLOR_HEX = "#00e5ff"
ALIGNMENT_SNAP_MARKER_ALPHA = 0.6
ALIGNMENT_SNAP_MARKER_SIZE_PX = 6

#: Bounds shared by the preference Range traits and the settings-sidebar
#: spinners (one source, so they cannot drift apart).
ALIGNMENT_SNAP_RADIUS_MIN_PX, ALIGNMENT_SNAP_RADIUS_MAX_PX = 0, 200
ALIGNMENT_HANDLE_RADIUS_MIN_PX, ALIGNMENT_HANDLE_RADIUS_MAX_PX = 2, 40
ALIGNMENT_FRAME_WIDTH_MIN_PX, ALIGNMENT_FRAME_WIDTH_MAX_PX = 1, 20
ALIGNMENT_SNAP_MARKER_SIZE_MIN_PX, ALIGNMENT_SNAP_MARKER_SIZE_MAX_PX = 1, 30

#: Width of the offscreen device-SVG render behind the endpoint pane —
#: enough resolution to zoom into electrode corners without an
#: excessive image.
ALIGNMENT_DEVICE_RENDER_WIDTH_PX = 1400

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
# The feed owns its preview state: the device viewer shows its video layer
# only while feed.streaming reports True (e.g. the fluorescence pane's
# "Device View Stream" checkbox). Captures here are display grabs for
# every feed; raw (16-bit) sensor captures are the source plugin's own
# concern (the fluorescence capture chain writes its own burst folders).
CAMERA_SOURCES = "device_viewer.camera_sources"

# ---------------------------------------------------------------------------
# Electrode zones (#596): named, colored electrode regions drawn on the
# device view. The model lives in models/zones.py.
# ---------------------------------------------------------------------------

# Device-view interaction modes added to DeviceViewMainModel.mode. Editing a
# region is ZONE_DRAW_MODE with ZoneLayerManager.editing_region set.
ZONE_DRAW_MODE = "zone"
ZONE_SELECT_MODE = "zone-select"
ZONE_MODES = (ZONE_DRAW_MODE, ZONE_SELECT_MODE)

# inkscape:label of the autogenerated SVG layer that stores regions.
ZONES_SVG_LAYER_LABEL = "Zones"

# Zone types seeded when preferences hold none (name, hex color).
DEFAULT_ZONE_TYPES = [
    ("heating", "#f5e050"),
    ("mixing", "#e06666"),
]

# Colors handed to newly added zone types, cycled in order.
ZONE_COLOR_CYCLE = [
    "#f5e050",
    "#e06666",
    "#6aa84f",
    "#6d9eeb",
    "#c27ba0",
    "#f6b26b",
]

# Region fill opacity at 100 % on the alpha table; overlapping regions blend.
ZONE_FILL_OPACITY = 0.43

# Dashed-highlight color when a ctrl+drag subtracts from the pending selection.
ZONE_SUBTRACT_PREVIEW_COLOR = "#d32f2f"

# Scene z-order: electrode fill sits at 0 and channel labels at 1, so zones
# and their previews stack between them.
ZONE_REGION_Z_VALUE = 0.5
ZONE_PENDING_Z_VALUE = 0.6
ZONE_BAND_Z_VALUE = 0.7

# Cosmetic outline widths (px); the selected region draws thicker.
ZONE_OUTLINE_PEN_WIDTH = 2
ZONE_SELECTED_OUTLINE_PEN_WIDTH = 4

# A press/release within this screen distance is a click (toggle one
# electrode), anything further is a rubber-band drag.
ZONE_CLICK_DRAG_THRESHOLD_PX = 4

# Fraction of the smallest inter-electrode gap used as the morphological
# closing distance for a region's union outline: bridges the gap between
# adjacent members without bridging a skipped-electrode hole.
ZONE_OUTLINE_GAP_CLOSING_FRACTION = 0.6

# Gap between a region/selection corner and its floating button strip.
ZONE_OVERLAY_MARGIN_PX = 8

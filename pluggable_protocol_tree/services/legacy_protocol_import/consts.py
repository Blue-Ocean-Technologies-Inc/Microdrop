"""Constants for importing protocols authored in the Python 2 MicroDrop
(github.com/sci-bots/microdrop)."""

# --- legacy Device Folder layout ---
DEVICE_SVG_FILENAME = "device.svg"
PROTOCOLS_DIR_NAME = "protocols"
DEVICES_DIR_NAME = "devices"

# --- default root path offered by the import dialog ---
DEFAULT_MICRODROP_DIR_NAME = "MicroDrop"
DEFAULT_DOCUMENTS_DIR_NAME = "Documents"

# --- import dialog: sentinel for "nothing selected" in a combo box ---
NO_SELECTION_INDEX = -1

# --- legacy plugin names, as they appear in Step.plugin_data ---
ELECTRODE_CONTROLLER_PLUGIN = "microdrop.electrode_controller_plugin"
DROPLET_PLANNING_PLUGIN = "droplet_planning_plugin"
STEP_LABEL_PLUGIN = "step_label_plugin"
USER_PROMPT_PLUGIN = "user_prompt_plugin"
DROPBOT_PLUGIN = "dropbot_plugin"
DMF_DEVICE_UI_PLUGIN = "dmf_device_ui_plugin"
MR_BOX_PLUGIN = "mr_box_plugin"
ZIKA_BOX_PLUGIN = "zika_box_plugin"
PLATEAU_DETECTION_PLUGIN = "plateau_detection_plugin"

# --- module prefixes that no longer exist and are stubbed while unpickling ---
LEGACY_STUBBED_MODULE_PREFIXES = (
    "microdrop", "microdrop_utility", "flatland", "pygtkhelpers",
)

# --- module a legacy protocol's top-level pickled object (Protocol, or a
# future Step-first layout) is a GLOBAL reference into. Used by the
# structural is_legacy_protocol_file probe (pickletools.genops opcode scan,
# not an unpickle) to recognise a legacy protocol file without executing
# anything from it. ---
MICRODROP_PROTOCOL_MODULE = "microdrop.protocol"

# --- pandas index classes removed in pandas 2.x, remapped to pandas.Index ---
REMOVED_PANDAS_INDEX_MODULE = "pandas.core.indexes.numeric"
REMOVED_PANDAS_INDEX_CLASSES = frozenset(
    {"Int64Index", "Float64Index", "UInt64Index"})

# --- the legacy protocol format version this importer understands ---
SUPPORTED_LEGACY_PROTOCOL_VERSION = "0.2.0"

# --- new-format column / compound-field ids written by the converter ---
NAME_COLUMN_ID = "name"
VOLTAGE_COLUMN_ID = "voltage"
FREQUENCY_COLUMN_ID = "frequency"
DURATION_COLUMN_ID = "duration_s"
ELECTRODES_COLUMN_ID = "electrodes"
ROUTES_COLUMN_ID = "routes"
ROUTE_REPETITIONS_COLUMN_ID = "route_repetitions"
REPEAT_DURATION_COLUMN_ID = "repeat_duration"
REPEAT_DURATION_CONTROLS_FLAG = "repeat_duration_controls"
TRAIL_LENGTH_COLUMN_ID = "trail_length"
MESSAGE_PROMPT_COLUMN_ID = "message_prompt"
VOLUME_THRESHOLD_COLUMN_ID = "volume_threshold"
VIDEO_COLUMN_ID = "video"
REPETITIONS_COLUMN_ID = "repetitions"
SET_MAGNET_FIELD_ID = "set_magnet"
MAGNET_ON_FIELD_ID = "magnet_on"
SET_TEMPERATURE_FIELD_ID = "set_temperature"
TARGET_TEMPERATURE_FIELD_ID = "target_temperature_c"

# --- legacy field names, as they appear inside each plugin's value dict ---
LEGACY_VOLTAGE_FIELD = "Voltage (V)"
LEGACY_FREQUENCY_FIELD = "Frequency (Hz)"
LEGACY_DURATION_FIELD = "Duration (s)"
LEGACY_ELECTRODE_STATES_FIELD = "electrode_states"
LEGACY_DROP_ROUTES_FIELD = "drop_routes"
LEGACY_ROUTE_REPEATS_FIELD = "route_repeats"
LEGACY_REPEAT_DURATION_FIELD = "repeat_duration_s"
LEGACY_TRAIL_LENGTH_FIELD = "trail_length"
LEGACY_LABEL_FIELD = "label"
LEGACY_MESSAGE_FIELD = "message"
LEGACY_VOLUME_THRESHOLD_FIELD = "volume_threshold"
LEGACY_VIDEO_ENABLED_FIELD = "video_enabled"
LEGACY_MAGNET_FIELD = "Magnet"
LEGACY_HEATER_FIELD = "Heater"
LEGACY_HEATER_TEMPERATURE_FIELD = "Heater_temperature"

# --- drop_routes DataFrame columns ---
LEGACY_ROUTE_INDEX_COLUMN = "route_i"
LEGACY_ROUTE_ELECTRODE_COLUMN = "electrode_i"
LEGACY_ROUTE_TRANSITION_COLUMN = "transition_i"

# --- legacy fields with no equivalent; recorded in the report and dropped ---
DROPPED_LEGACY_FIELDS = {
    MR_BOX_PLUGIN: (
        "Pump", "Pump_frequency_(hz)", "Pump_duration_(s)", "Measure_PMT",
        "Measurement_duration_(s)", "Auto pump electrode",
        "Magnet_height(mm)",
    ),
    USER_PROMPT_PLUGIN: ("schema",),
    PLATEAU_DETECTION_PLUGIN: (
        "Plateau Detection", "Check Split", "Calibrate Threshold",
    ),
}

# --- volume_threshold: legacy 0-1 fraction -> new 0-100 integer percent ---
VOLUME_THRESHOLD_PERCENT_SCALE = 100
VOLUME_THRESHOLD_MIN_PERCENT = 0
VOLUME_THRESHOLD_MAX_PERCENT = 100

# --- name of the wrapper group that carries a repeated protocol's n_repeats ---
IMPORTED_PROTOCOL_GROUP_NAME = "Imported protocol"

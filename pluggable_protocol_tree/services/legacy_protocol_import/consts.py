"""Constants for importing protocols authored in the Python 2 MicroDrop
(github.com/sci-bots/microdrop)."""

# --- legacy Device Folder layout ---
DEVICE_SVG_FILENAME = "device.svg"
PROTOCOLS_DIR_NAME = "protocols"
DEVICES_DIR_NAME = "devices"

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

# --- pandas index classes removed in pandas 2.x, remapped to pandas.Index ---
REMOVED_PANDAS_INDEX_MODULE = "pandas.core.indexes.numeric"
REMOVED_PANDAS_INDEX_CLASSES = frozenset(
    {"Int64Index", "Float64Index", "UInt64Index"})

# --- the legacy protocol format version this importer understands ---
SUPPORTED_LEGACY_PROTOCOL_VERSION = "0.2.0"

# --- sample Device Folders used by the unit tests; absent on most machines ---
LEGACY_SAMPLE_DEVICE_FOLDERS = (
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/August 2022 Quanterix test",
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/Duo Fluo v2 28x",
    "C:/Users/Info/AppData/Roaming/JetBrains/PyCharm2025.2/scratches/"
    "legacy_protocols/Zika-4d Mirror",
    "C:/Users/Info/Documents/MicroDrop/devices/DMF-90-pin-array",
)

# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Installed plugin packages advertise this entry-point group and ship this
# TOML manifest (see PLUGIN_DEVELOPMENT.md).
ENTRY_POINT_GROUP = "microdrop.plugins"
MANIFEST_RESOURCE = "microdrop_plugin.toml"

# The hosted conda channel Browse Plugins installs from.
PLUGIN_CHANNEL_URL = "https://prefix.dev/microdrop-plugins"

# Topic constants are the pub/sub contract — importing them cross-plugin is OK.
# Module-qualified because both devices name their topic START_DEVICE_MONITORING.
from peripheral_controller import consts as peripheral_controller_consts
from heater_controller import consts as heater_controller_consts

# App-globals keys persisting each group's enabled state across runs
# (owned by this plugin; aggregated per the APP_GLOBALS_KEYS convention).
ZSTAGE_UI_GROUP_ENABLED_KEY = "plugin_group_enabled.zstage_ui"
ZSTAGE_BACKEND_GROUP_ENABLED_KEY = "plugin_group_enabled.zstage_backend"
HEATER_UI_GROUP_ENABLED_KEY = "plugin_group_enabled.heater_ui"
HEATER_BACKEND_GROUP_ENABLED_KEY = "plugin_group_enabled.heater_backend"
APP_GLOBALS_KEYS = [
    ZSTAGE_UI_GROUP_ENABLED_KEY, ZSTAGE_BACKEND_GROUP_ENABLED_KEY,
    HEATER_UI_GROUP_ENABLED_KEY, HEATER_BACKEND_GROUP_ENABLED_KEY,
]

# Built-in toggleable plugin groups. Each device splits into a UI group
# (dock pane + protocol-controls column — the protocol tree hot-swaps
# columns when PROTOCOL_COLUMNS contributions change) and a BACKEND group
# (board driver), so split frontend/backend processes each manage their own
# half and the Manage Plugins window shows them separately. Plugin classes
# are dotted "module:Class" specs resolved lazily at enable/adopt time, so
# plugin_management never imports a device plugin at its own import time.
# Load order = list order; unload is the reverse. post_enable_publish_topic
# re-kicks the device's connection search when a BACKEND group is hot-enabled
# (the plugins' own application_initialized probes never fire after startup).
BUILTIN_PLUGIN_GROUPS = (
    {
        "name": "zstage_ui",
        "label": "Z-Stage UI (controls/status dock-pane + protocol column + statusbar icon)",
        "plugin_specs": [
            "peripherals_ui.plugin:PeripheralUiPlugin",
            "peripheral_protocol_controls.plugin:PeripheralProtocolControlsPlugin",
        ],
        "enabled_key": ZSTAGE_UI_GROUP_ENABLED_KEY,
    },
    {
        "name": "zstage_backend",
        "label": "Z-Stage backend (board driver)",
        "plugin_specs": [
            "peripheral_controller.plugin:PeripheralControllerPlugin",
        ],
        "enabled_key": ZSTAGE_BACKEND_GROUP_ENABLED_KEY,
        "post_enable_publish_topic":
            peripheral_controller_consts.START_DEVICE_MONITORING,
    },
    {
        "name": "heater_ui",
        "label": "Heater UI (status/controls and plotting dock-pane + protocol column + statusbar icon)",
        "plugin_specs": [
            "heater_controls_ui.plugin:HeaterControlsUiPlugin",
            "heater_protocol_controls.plugin:HeaterProtocolControlsPlugin",
        ],
        "enabled_key": HEATER_UI_GROUP_ENABLED_KEY,
    },
    {
        "name": "heater_backend",
        "label": "Heater backend (board driver)",
        "plugin_specs": [
            "heater_controller.plugin:HeaterControllerPlugin",
        ],
        "enabled_key": HEATER_BACKEND_GROUP_ENABLED_KEY,
        "post_enable_publish_topic":
            heater_controller_consts.START_DEVICE_MONITORING,
    },
)

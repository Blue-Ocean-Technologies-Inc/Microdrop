# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topic constants are the pub/sub contract — importing them cross-plugin is OK.
# Module-qualified because both devices name their topic START_DEVICE_MONITORING.
from peripheral_controller import consts as peripheral_controller_consts
from heater_controller import consts as heater_controller_consts

# App-globals keys persisting each group's enabled state across runs
# (owned by this plugin; aggregated per the APP_GLOBALS_KEYS convention).
ZSTAGE_GROUP_ENABLED_KEY = "plugin_group_enabled.zstage"
HEATER_GROUP_ENABLED_KEY = "plugin_group_enabled.heater"
APP_GLOBALS_KEYS = [ZSTAGE_GROUP_ENABLED_KEY, HEATER_GROUP_ENABLED_KEY]

# Built-in toggleable plugin groups. Plugin classes are dotted "module:Class"
# specs resolved lazily at enable/adopt time, so plugin_management never
# imports a device plugin at its own import time. Load order = list order;
# unload is the reverse. post_enable_publish_topic re-kicks the device's
# connection search on a hot enable (the plugins' own
# application_initialized probes never fire after startup).
BUILTIN_PLUGIN_GROUPS = (
    {
        "name": "zstage",
        "label": "Z-Stage (peripheral board)",
        "plugin_specs": [
            "peripherals_ui.plugin:PeripheralUiPlugin",
            "peripheral_controller.plugin:PeripheralControllerPlugin",
        ],
        "enabled_key": ZSTAGE_GROUP_ENABLED_KEY,
        "post_enable_publish_topic":
            peripheral_controller_consts.START_DEVICE_MONITORING,
    },
    {
        "name": "heater",
        "label": "Heater (peripheral board)",
        "plugin_specs": [
            "heater_controls_ui.plugin:HeaterControlsUiPlugin",
            "heater_controller.plugin:HeaterControllerPlugin",
        ],
        "enabled_key": HEATER_GROUP_ENABLED_KEY,
        "post_enable_publish_topic":
            heater_controller_consts.START_DEVICE_MONITORING,
    },
)

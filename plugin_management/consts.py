# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Microdrop utils imports.
from microdrop_utils.system_config import is_rpi

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# Installed plugin packages advertise this entry-point group and ship this
# TOML manifest (see PLUGIN_DEVELOPMENT.md).
ENTRY_POINT_GROUP = "microdrop.plugins"
MANIFEST_RESOURCE = "microdrop_plugin.toml"

# The hosted conda channel Browse Plugins installs from.
PLUGIN_CHANNEL_URL = "https://prefix.dev/microdrop-plugins"

# Built-in toggleable plugin groups: groups whose code ships inside the app
# itself. Every other group (heater, magnet/Z-Stage, ...) comes from an
# installed package's microdrop_plugin.toml manifest, discovered via the
# microdrop.plugins entry point. Each dict holds PluginGroup trait values; a
# built-in gets the same Manage Plugins checkbox, persisted flag and hot
# load/unload as a manifest group, but never lists as an installed package
# since it cannot be uninstalled. Its plugins must not also sit in a static
# startup list in examples/plugin_consts.py.
BUILTIN_PLUGIN_GROUPS = (
    # The battery icon reads the rpi-battery-monitor daemon's status file,
    # which only the portable rig's Pi runs: on by default there, off
    # elsewhere until ticked (e.g. to test with the
    # MICRODROP_RPI_BATTERY_STATUS_FILE override).
    {
        "name": "rpi_battery_ui",
        "label": "Battery status icon (portable rig)",
        "plugin_specs": ["rpi_battery_status.plugin:RpiBatteryStatusPlugin"],
        "enabled_key": "plugin_group_enabled.rpi_battery_ui",
        "default_enabled": is_rpi(),
    },
)

# Application-preferences node holding each group's persisted enabled flag
# (full path: f"{GROUP_ENABLED_PREFERENCES_PATH}.{enabled_key}"). The flags
# must live in the preferences FILE — the Redis-backed app_globals runs with
# persistence disabled (redis.conf: save "") and dies with the app.
GROUP_ENABLED_PREFERENCES_PATH = "microdrop.plugin_groups"

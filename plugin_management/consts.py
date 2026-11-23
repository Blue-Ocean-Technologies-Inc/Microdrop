# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from pathlib import Path

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR, GREY, INFO_COLOR, SUCCESS_COLOR
from microdrop_style.icons.icons import ICON_CHECK, ICON_CLOSE, ICON_EXTENSION

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import (
    LOAD_FAILED,
    LOAD_LOADED,
    LOAD_LOADING,
    LOAD_PENDING,
)
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

#: Help > Tutorials page, built from resources/plugin_management.src.html.
PLUGIN_MANAGEMENT_TUTORIAL_HTML_PATH = (
    Path(__file__).parent / "resources" / "plugin_management.html"
)

#: Glyph (icon font) and colour of each plugin load state, shared by the
#: status-bar indicator (aggregate state) and the load-status panel (per row).
PLUGIN_LOAD_STATE_GLYPHS = {
    LOAD_PENDING: ICON_EXTENSION,
    LOAD_LOADING: ICON_EXTENSION,
    LOAD_LOADED: ICON_CHECK,
    LOAD_FAILED: ICON_CLOSE,
}

PLUGIN_LOAD_STATE_COLORS = {
    LOAD_PENDING: GREY["dark"],
    LOAD_LOADING: INFO_COLOR,
    LOAD_LOADED: SUCCESS_COLOR,
    LOAD_FAILED: ERROR_COLOR,
}

#: Monospace text for the load-status panel's traceback area.
TRACEBACK_STYLE_SHEET = 'font-family: Consolas, "Courier New", monospace;'

#: The plugin load list as a section of the notifications pane: its id
#: (NOTIFICATIONS_SHOW_PANEL names it), header and place, first.
LOAD_STATUS_SECTION_ID = f"{PKG}.load_status"
LOAD_STATUS_SECTION_TITLE = "Plugins"
LOAD_STATUS_SECTION_ORDER = 0

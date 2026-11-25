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

# Microdrop package imports.
from dropbot_controller.consts import SHORTS_DETECTED
from message_router.consts import PKG as message_router_PKG
from microdrop_status_bar.consts import PKG as microdrop_status_bar_PKG
from plugin_management.consts import PKG as plugin_management_PKG

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import get_current_utc_datetime

# Logger import.
from logger.consts import PKG as logger_PKG

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Ids of the plugins MicroDrop cannot run without — the default of
#: ``MicrodropApplication.essential_plugin_ids``. A failure to start one of
#: these fails the launch; any other plugin that fails is skipped and rolled
#: back. The REQUIRED_PLUGINS of examples/plugin_consts.py, then the
#: application shell: this package's plugin, Envisage's Tasks plugin, the
#: status bar, and plugin management (which reports the failures). Envisage's
#: own ids are literals: a Plugin's id cannot be read off its class.
ESSENTIAL_PLUGIN_IDS = [
    "envisage.core",
    f"{message_router_PKG}.plugin",
    f"{logger_PKG}.plugin",
    f"{PKG}.plugin",
    "envisage.ui.tasks",
    f"{microdrop_status_bar_PKG}.plugin",
    f"{plugin_management_PKG}.plugin",
]

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {f"{PKG}_listener": [SHORTS_DETECTED]}

# Topics published
ADVANCED_MODE_CHANGE = "microdrop/advanced_mode_change"

# File-menu skeleton: the shell fixes two sections, the plugins' submenus
# then Exit. Plugins add into the first via
# SchemaAddition(path=f"MenuBar/File/{FILE_MENU_SUBMENUS_GROUP_ID}") and
# declare their submenu's order within it with after= hints. Pyface matches
# a hint against the other additions' id=, so an addition that others
# order against sets id= to its menu id.
FILE_MENU_SUBMENUS_GROUP_ID = "SubmenusGroup"
FILE_MENU_EXIT_GROUP_ID = "ExitGroup"

#: QApplication dynamic property that is True while Touch mode is on. It
#: flips together with the touch stylesheet block, so every widget gets a
#: StyleChange event to re-read it on. Read it with helpers.is_touch_mode.
TOUCH_MODE_APP_PROPERTY = "microdropTouchMode"


# App-wide colour-scheme override (MicrodropPreferences.color_scheme). The
# light/dark values match microdrop_style.helpers.QT_THEME_NAMES, which maps
# them onto Qt.ColorScheme; follow_system defers to the OS.
COLOR_SCHEME_FOLLOW_SYSTEM = "follow_system"
COLOR_SCHEME_LIGHT = "light"
COLOR_SCHEME_DARK = "dark"

# TraitsUI's EnumEditor sorts dict labels and strips a shared "n:" prefix,
# which is what orders the dropdown.
COLOR_SCHEME_LABELS = {
    COLOR_SCHEME_FOLLOW_SYSTEM: "1:Follow system",
    COLOR_SCHEME_LIGHT: "2:Light",
    COLOR_SCHEME_DARK: "3:Dark",
}

# Dock-separator colour (MicrodropPreferences.dock_separator_color_mode): the
# colour-scheme modes pick that theme's separator grey, custom uses
# MicrodropPreferences.dock_separator_color.
DOCK_SEPARATOR_COLOR_CUSTOM = "custom"

DOCK_SEPARATOR_COLOR_LABELS = {
    **COLOR_SCHEME_LABELS,
    DOCK_SEPARATOR_COLOR_CUSTOM: "4:Custom",
}

scibots_icon_path = Path(__file__).parent / "resources" / "scibots-icon.png"
CHANGELOG_PATH = Path(__file__).parent.parent / "CHANGELOG.md"

#: The CHANGELOG.md text the What's New dialog last showed, in the
#: application home; the news plugin keeps it current when it shows notes.
PREVIOUS_CHANGELOG_FILENAME = ".previous_changelog"

APP_GLOBALS_REDIS_HASH = "microdrop_application_globals"

# app_globals keys (stored in APP_GLOBALS_REDIS_HASH via the redis client)
ADVANCED_MODE_KEY = "microdrop.advanced_mode"  # advanced-mode toggle flag

APP_GLOBALS_KEYS = [
    ADVANCED_MODE_KEY,
]

EXPERIMENT_DIR = get_current_utc_datetime()

#: Help > Tutorials page, built from resources/shortcuts.src.html.
SHORTCUTS_TUTORIAL_HTML_PATH = Path(__file__).parent / "resources" / "shortcuts.html"

#: Help > Tutorials page, built from resources/preferences.src.html.
PREFERENCES_TUTORIAL_HTML_PATH = (
    Path(__file__).parent / "resources" / "preferences.html"
)

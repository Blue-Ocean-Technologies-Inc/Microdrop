# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Subdirectory of the application's ``state_location`` holding the presets.
PRESETS_DIRNAME = "layout_presets"

#: Each preset is one pickled ``TaskWindowLayout`` named ``<name><suffix>``.
PRESET_FILE_SUFFIX = ".pickle"

#: Default names are ``<stem>-1``, ``<stem>-2``, ... — the first one free.
DEFAULT_PRESET_STEM = "preset"

#: A preset name is a file stem, so it may not hold any of these.
INVALID_PRESET_NAME_CHARACTERS = '/\\:*?"<>|'

#: Device names Windows reserves whatever the extension.
RESERVED_PRESET_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)

#: View-menu placement: after the group holding Reset Layout.
VIEW_MENU_PATH = "MenuBar/View"
VIEW_MENU_LAYOUT_GROUP_ID = "LayoutGroup"
LAYOUT_PRESETS_GROUP_ID = f"{PKG}.view_menu_group"

LAYOUT_PRESETS_MENU_ID = f"{PKG}.presets_menu"
LAYOUT_PRESETS_ITEMS_GROUP_ID = f"{PKG}.presets_group"
LAYOUT_PRESETS_MENU_NAME = "Layout &Presets"
NO_LAYOUT_PRESETS_LABEL = "(No saved presets)"

SAVE_LAYOUT_PRESET_ACTION_ID = f"{PKG}.save_current_layout"
SAVE_LAYOUT_PRESET_ACTION_NAME = "Save Current &Layout..."
SAVE_LAYOUT_PRESET_DIALOG_TITLE = "Save Current Layout"
APPLY_LAYOUT_PRESET_DIALOG_TITLE = "Layout Presets"

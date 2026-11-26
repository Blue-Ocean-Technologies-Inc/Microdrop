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
import os
from pathlib import Path

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_VOLUME_ESTIMATE,
    PROTOCOL_GRID_DISPLAY_STATE,
    PROTOCOL_RUNNING,
)
from dropbot_preferences_ui.consts import VOLTAGE_FREQUENCY_RANGE_CHANGED
from notifications.consts import (
    TONE_CONNECTED,
    TONE_DISCONNECTED,
    NotificationCategorySpec,
)
from user_help_plugin.consts import tutorial_id

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR, GREY, SUCCESS_COLOR, WARNING_COLOR

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

HELP_PATH = os.path.join(os.path.dirname(__file__), "help")

listener_name = f"{PKG}_listener"

#: The DropBot connecting and disconnecting as notifications, each with its
#: own chime; both update one card, so unplugging and replugging does not
#: stack them up.
DROPBOT_CONNECTED_CATEGORY_ID = f"{PKG}.connected"
DROPBOT_DISCONNECTED_CATEGORY_ID = f"{PKG}.disconnected"
DROPBOT_CONNECTION_THREAD_ID = f"{PKG}.connection"

#: A chip put in or taken out, the same way on its own card.
DROPBOT_CHIP_INSERTED_CATEGORY_ID = f"{PKG}.chip_inserted"
DROPBOT_CHIP_REMOVED_CATEGORY_ID = f"{PKG}.chip_removed"
DROPBOT_CHIP_THREAD_ID = f"{PKG}.chip"

NOTIFICATION_CATEGORY_SPECS = [
    NotificationCategorySpec(
        id=DROPBOT_CONNECTED_CATEGORY_ID,
        group="DropBot",
        label="Connected",
        description="The DropBot connects, or connects again.",
        tone=TONE_CONNECTED,
    ),
    NotificationCategorySpec(
        id=DROPBOT_DISCONNECTED_CATEGORY_ID,
        group="DropBot",
        label="Disconnected",
        description="The DropBot is unplugged or its connection is lost.",
        tone=TONE_DISCONNECTED,
    ),
    NotificationCategorySpec(
        id=DROPBOT_CHIP_INSERTED_CATEGORY_ID,
        group="DropBot",
        label="Chip inserted",
        description="A chip is detected in the DropBot.",
        tone=TONE_CONNECTED,
    ),
    NotificationCategorySpec(
        id=DROPBOT_CHIP_REMOVED_CATEGORY_ID,
        group="DropBot",
        label="Chip removed",
        description="The chip is taken out of a connected DropBot.",
        tone=TONE_DISCONNECTED,
    ),
]

# Single listener subscribing to all dropbot signals + calibration data
ACTOR_TOPIC_DICT = {
    listener_name: [
        "dropbot/signals/#",
        "hardware/signals/#",
        "ui/calibration_data",
        DEVICE_VIEWER_VOLUME_ESTIMATE,
        PROTOCOL_RUNNING,
        PROTOCOL_GRID_DISPLAY_STATE,
        VOLTAGE_FREQUENCY_RANGE_CHANGED,
    ]
}

# Image paths
current_folder_path = os.path.dirname(os.path.abspath(__file__))
DROPBOT_IMAGE = os.path.join(current_folder_path, "images", "dropbot.png")
DROPBOT_CHIP_INSERTED_IMAGE = os.path.join(
    current_folder_path, "images", "dropbot-chip-inserted.png"
)

NUM_CAPACITANCE_READINGS_AVERAGED = 5

# Dielectric materials and their relative permittivity values.
# Used to calculate dielectric thickness from device capacitance via:
#   d = epsilon * epsilon_0 / C_device
DIELECTRIC_MATERIALS = {
    "Pick a dielectric...": float("nan"),
    "Parylene C": 3.1,
    "CYTOP": 2.1,
    "Teflon AF": 1.93,
    "SiO2": 3.9,
    "SU-8": 3.2,
    "Parylene N": 2.65,
    "Parylene D": 2.84,
    "PDMS": 2.7,
    "Si3N4": 7.5,
    "Kapton": 3.4,
}

# ---------------------------------------------------------------------------
# app_globals keys (stored in APP_GLOBALS_REDIS_HASH via the redis client)
# ---------------------------------------------------------------------------
# The DIELECTRIC_MATERIALS name picked in the status pane.
DIELECTRIC_MATERIAL_KEY = "dropbot.dielectric_material"

APP_GLOBALS_KEYS = [DIELECTRIC_MATERIAL_KEY]

# Status colors
disconnected_color = GREY["lighter"]
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR
halted_color = ERROR_COLOR

#: Help > Tutorials page, built from resources/dropbot_status.src.html.
DROPBOT_STATUS_TUTORIAL_HTML_PATH = (
    Path(__file__).parent / "resources" / "dropbot_status.html"
)

#: The tutorial's id for OPEN_TUTORIAL, and the sections (ids in its page)
#: other plugins' help links open: connecting, inserting a chip, the volume
#: readout, and the Tools > Dropbot self tests.
DROPBOT_STATUS_TUTORIAL_ID = tutorial_id(DROPBOT_STATUS_TUTORIAL_HTML_PATH)
CONNECTION_TUTORIAL_ANCHOR = "connection"
CHIP_STATUS_TUTORIAL_ANCHOR = "chip-status"
VOLUME_TUTORIAL_ANCHOR = "volume"
SELF_TESTS_TUTORIAL_ANCHOR = "part-tools"

#: The tutorial's sections on the halted and no-power dialogs, the help
#: links of the entries those dialogs leave in the notifications drawer.
HALTED_DIALOG_TUTORIAL_ANCHOR = "dlg-halted"
NO_POWER_DIALOG_TUTORIAL_ANCHOR = "dlg-nopower"

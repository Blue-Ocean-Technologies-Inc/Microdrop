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

# Microdrop utils imports.
from microdrop_utils.datetime_helpers import get_current_utc_datetime

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topics actor declared by plugin subscribes to
ACTOR_TOPIC_DICT = {f"{PKG}_listener": [SHORTS_DETECTED]}

# Topics published
ADVANCED_MODE_CHANGE = "microdrop/advanced_mode_change"


scibots_icon_path = Path(__file__).parent / "resources" / "scibots-icon.png"
CHANGELOG_PATH = Path(__file__).parent.parent / "CHANGELOG.md"
application_home_directory = Path.home() / "Documents" / "MicroDropNextGen"
APP_GLOBALS_REDIS_HASH = "microdrop_application_globals"

# app_globals keys (stored in APP_GLOBALS_REDIS_HASH via the redis client)
ADVANCED_MODE_KEY = "microdrop.advanced_mode"  # advanced-mode toggle flag

APP_GLOBALS_KEYS = [
    ADVANCED_MODE_KEY,
]

EXPERIMENT_DIR = get_current_utc_datetime()

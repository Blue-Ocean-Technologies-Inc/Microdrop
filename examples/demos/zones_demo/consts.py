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
import device_viewer

# Bundled devices shipped with the device_viewer package; the demo opens one
# of these by default and the file dialog starts here.
DEVICE_SVG_RESOURCES_DIR = Path(device_viewer.__file__).parent / "resources" / "devices"
DEFAULT_DEVICE_SVG_PATH = DEVICE_SVG_RESOURCES_DIR / "2x3device.svg"

ELECTRODE_FILL_COLOR = "#2b4d9e"
ELECTRODE_Z_VALUE = 0

# Canvas interaction mode when neither zone mode is active (the shipped
# manager's own "" mode). ZONE_DRAW_MODE / ZONE_SELECT_MODE come from
# device_viewer.consts.
PAN_MODE = "pan"

SIDEBAR_WIDTH = 280

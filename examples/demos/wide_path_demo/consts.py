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

DEVICE_SVG_RESOURCES_DIR = Path(device_viewer.__file__).parent / "resources" / "devices"
DEFAULT_DEVICE_SVG_PATH = DEVICE_SVG_RESOURCES_DIR / "2x3device.svg"

ELECTRODE_FILL_COLOR = "#2b4d9e"
CLICK_DRAG_THRESHOLD_PX = 4
SIDEBAR_WIDTH = 300

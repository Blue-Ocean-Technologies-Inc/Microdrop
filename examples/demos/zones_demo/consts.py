# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from pathlib import Path

import device_viewer

# Bundled devices shipped with the device_viewer package; the demo opens one
# of these by default and the file dialog starts here.
DEVICE_SVG_RESOURCES_DIR = Path(device_viewer.__file__).parent / "resources" / "devices"
DEFAULT_DEVICE_SVG_PATH = DEVICE_SVG_RESOURCES_DIR / "2x3device.svg"

# Seed zone types shown on first launch (name, hex color) — from the mockup.
DEFAULT_ZONE_TYPES = [
    ("heating", "#f5e050"),
    ("mixing", "#e06666"),
]

# Colors handed to newly added zone types, cycled in order.
ZONE_COLOR_CYCLE = [
    "#f5e050",
    "#e06666",
    "#6aa84f",
    "#6d9eeb",
    "#c27ba0",
    "#f6b26b",
]

ELECTRODE_FILL_COLOR = "#2b4d9e"

# Rubber-band preview color when a ctrl+drag in draw/edit mode will subtract
# from the pending selection instead of adding to it (the active zone type's
# color reads as additive, so subtraction needs a visually distinct color).
SUBTRACT_PREVIEW_COLOR = "#d32f2f"

# 0-255 fill opacity for zone regions; overlapping regions blend visually.
ZONE_FILL_ALPHA = 110

ELECTRODE_Z_VALUE = 0
ZONE_REGION_Z_VALUE = 1

# Cosmetic outline pen widths for committed zone regions; the selected region
# draws thicker so the selection is visible on the canvas.
ZONE_OUTLINE_PEN_WIDTH = 2
SELECTED_ZONE_OUTLINE_PEN_WIDTH = 4

# Live rubber-band capture preview draws above committed regions.
CAPTURE_PREVIEW_Z_VALUE = 2

# Gap between the anchor item and the floating overlay button strips.
COMMIT_OVERLAY_MARGIN_PX = 8

# Canvas interaction modes (the sidebar radio row drives these). Edit is
# draw-mode interaction over an existing region's electrode set; it needs a
# selected region to enter.
PAN_MODE = "pan"
ZONE_DRAW_MODE = "zone"
SELECT_MODE = "select"
EDIT_MODE = "edit"

# A press/release within this distance (view px) counts as a click (toggle
# one electrode) rather than a rubber-band drag.
ZONE_CLICK_DRAG_THRESHOLD_PX = 4

# Fraction of the smallest inter-electrode gap used as the morphological
# closing distance when computing a region's union outline: large enough to
# bridge the gap between adjacent member electrodes, small enough not to
# bridge a skipped-electrode hole.
OUTLINE_GAP_CLOSING_FRACTION = 0.6

SIDEBAR_WIDTH = 280

# Max snapshots kept by the manager's undo stack.
UNDO_STACK_LIMIT = 20

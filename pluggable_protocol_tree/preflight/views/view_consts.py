# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Look and timing of the pre-flight pill and card. The surface, radius,
padding, motion and stripe values are the notifications drawer's, shared
through ``microdrop_style.panel_metrics``."""

#: How far the panel slides up as it opens, px.
SLIDE_PX = 10

#: The panel's width, px.
PANEL_WIDTH = 320

#: Every row's height, px: problem cards and quiet rows alike.
ROW_HEIGHT = 26

#: Gap between rows, px.
ROW_GAP = 2

#: Space above a group label in the expanded list, px.
GROUP_GAP = 4

#: Gap between the panel and the pill, px.
ANCHOR_GAP = 4

#: The panel's least distance from the window's edges, px.
WINDOW_MARGIN = 8

#: A row's category glyph and its status badge, px.
GLYPH_SIZE = 18
BADGE_SIZE = 11

#: Category glyph per check id (Material Symbols ligatures): an exact id
#: first, else the prefix before ":" (column checks such as "video:camera"
#: and the unused-column rows).
CHECK_GLYPHS = {
    "voltage:dropbot": "usb",
    "voltage:hv_supply": "bolt",
    "voltage:chip": "memory",
    "chip": "memory",
    "voltage:limits": "tune",
    "no_empty_steps": "check_box_outline_blank",
    "electrodes_exist": "grid_on",
    "routes_valid": "route",
    "disabled_channels": "block",
    "unused_column": "view_column",
    "ack_wait_off": "timer_off",
    "frequency": "tune",
    "video": "photo_camera",
    "heater": "thermostat",
    "magnet": "settings_input_component",
    "folder_writable": "folder",
    "disk_space": "hard_drive",
}

#: Status badge per status (Material Symbols ligatures): a shape each, so
#: status never rests on colour alone. A skipped (not checked) row shows a
#: grey dash, never a tick.
STATUS_BADGES = {
    "pass": "check_circle",
    "warn": "warning",
    "fail": "cancel",
    "skip": "remove",
}

#: Glyphs for the mute controls and for run state.
ICON_MUTE = "notifications_off"
ICON_UNMUTE = "notifications_active"
ICON_RUNNING = "play_circle"
ICON_EXPAND = "expand_more"
ICON_COLLAPSE = "expand_less"

#: The card header's settings gear and the settings face's way back: the
#: glyphs the notifications drawer header and the device-viewer sidebar use.
ICON_SETTINGS = "settings"
ICON_BACK = "chevron_left"

#: How long "All clear" shows on the pill, ms.
FLASH_MS = 600

#: A row new since the last display fades in over this long, ms.
ENTRANCE_MS = 150

#: The pill's re-checking ring: fade in/out, minimum time shown, and one
#: turn, ms.
RING_FADE_MS = 120
RING_MIN_MS = 300
RING_TURN_MS = 900


def check_glyph(check_id):
    """The category glyph for ``check_id``."""
    if check_id in CHECK_GLYPHS:
        return CHECK_GLYPHS[check_id]

    return CHECK_GLYPHS.get(check_id.split(":")[0], "help")

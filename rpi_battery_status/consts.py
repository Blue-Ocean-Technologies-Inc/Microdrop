# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Constants for the rpi_battery_status plugin."""

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR, GREY, SUCCESS_COLOR, WARNING_COLOR

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# The plugin reads a file the rpi-battery-monitor daemon writes; it publishes
# and subscribes to no topics.
ACTOR_TOPIC_DICT = {}

# ---------------------------------------------------------------------------
# The daemon's status file: $XDG_RUNTIME_DIR/<dir>/<file>, else
# /tmp/rpi-battery-monitor-<uid>/<dir>/<file>. Replaced atomically every poll.
# ---------------------------------------------------------------------------
STATUS_DIR_NAME = "rpi-battery-monitor"
STATUS_FILE_NAME = "status.json"
FALLBACK_RUNTIME_DIR_TEMPLATE = "/tmp/rpi-battery-monitor-{uid}"

#: Env var naming any status file to read instead (development, demos).
STATUS_FILE_ENV_VAR = "MICRODROP_RPI_BATTERY_STATUS_FILE"

#: A snapshot older than this (s) means the daemon stopped writing.
STALE_AFTER_S = 10

#: How often (ms) the status file is re-read. It lives on tmpfs, so a short
#: interval is free and charger plug/unplug shows within seconds.
POLL_INTERVAL_MS = 2000

#: Unknown time / amp-hour values arrive as null or as this sentinel.
UNKNOWN_SENTINEL = -1

#: Below this state of charge (%) the icon turns red.
CRITICAL_PERCENT = 15

#: Below this state of charge (%) the icon turns amber; green above.
LOW_PERCENT = 40

# ---------------------------------------------------------------------------
# Battery levels, in precedence order; they set the icon colour only.
# ---------------------------------------------------------------------------
LEVEL_UNAVAILABLE = "unavailable"  # no file, malformed, or stale snapshot
LEVEL_ABSENT = "absent"  # the sensor reads the charger rail, no pack
LEVEL_ALERT = "alert"  # the INA226 low-voltage ALERT is raised
LEVEL_CRITICAL = "critical"  # below CRITICAL_PERCENT
LEVEL_LOW = "low"  # below LOW_PERCENT
LEVEL_NORMAL = "normal"

#: Icon colour per level; levels missing here use the normal text colour.
LEVEL_COLORS = {
    LEVEL_UNAVAILABLE: GREY["lighter"],
    LEVEL_ABSENT: GREY["lighter"],
    LEVEL_ALERT: ERROR_COLOR,
    LEVEL_CRITICAL: ERROR_COLOR,
    LEVEL_LOW: WARNING_COLOR,
    LEVEL_NORMAL: SUCCESS_COLOR,
}

# ---------------------------------------------------------------------------
# Material Symbols ligatures (all present in the bundled Outlined font). The
# fill bucket indexes both lists: bucket = round(percentage / 100 * 7).
# ---------------------------------------------------------------------------
DISCHARGING_GLYPHS = [
    "battery_0_bar",
    "battery_1_bar",
    "battery_2_bar",
    "battery_3_bar",
    "battery_4_bar",
    "battery_5_bar",
    "battery_6_bar",
    "battery_full",
]

# The font has no charging glyph below 20 %, so the two lowest buckets share it.
CHARGING_GLYPHS = [
    "battery_charging_20",
    "battery_charging_20",
    "battery_charging_30",
    "battery_charging_50",
    "battery_charging_60",
    "battery_charging_80",
    "battery_charging_90",
    "battery_charging_full",
]

#: Glyph while the state of charge is unknown or meaningless.
UNKNOWN_GLYPH = "battery_unknown"

#: Percent text while the state of charge is unknown or meaningless.
UNKNOWN_PERCENT_TEXT = "--"

#: Details-panel wording for the daemon's soc_source values; any other
#: value is shown as it arrives.
SOC_SOURCE_TEXTS = {
    "coulomb": "coulomb counting",
    "voltage": "voltage curve",
    "blend": "blend",
}

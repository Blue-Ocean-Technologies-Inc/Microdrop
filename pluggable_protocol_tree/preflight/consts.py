# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Ids, mute keys and thresholds of the protocol pre-flight check."""

# Microdrop package imports.
from pluggable_protocol_tree.consts import ELECTRODES_COL_ID
from pluggable_protocol_tree.services.legacy_protocol_import.consts import (
    FREQUENCY_COLUMN_ID,
    VOLTAGE_COLUMN_ID,
)
from pluggable_protocol_tree.services.protocol_validator import ROUTES_COL_ID

#: The groups checks are listed under, in display order. ppt's built-ins
#: fill Protocol and Data; columns fill Hardware and Peripherals.
CATEGORIES = ["Hardware", "Protocol", "Peripherals", "Data"]

#: Every state a check can be in. "skip": cannot be judged in this run
#: (a hardware check in preview, or one whose prerequisite failed).
STATUSES = ["pass", "warn", "fail", "skip"]

#: ppt's built-in check ids: protocol structure and data only. Hardware is
#: checked by the columns that drive it.
CHECK_NO_EMPTY_STEPS = "no_empty_steps"
CHECK_ELECTRODES_EXIST = "electrodes_exist"
CHECK_ROUTES_VALID = "routes_valid"
CHECK_DISABLED_CHANNELS = "disabled_channels"
CHECK_FOLDER_WRITABLE = "folder_writable"
CHECK_DISK_SPACE = "disk_space"

#: Prefix of the per-column unused-column checks: "unused_column:<col_id>".
UNUSED_COLUMN_PREFIX = "unused_column"

#: Prefix of the per-column ack-wait checks: "ack_wait_off:<col_id>".
ACK_WAIT_OFF_PREFIX = "ack_wait_off"

#: Mute scopes: until the next Run, or for good.
MUTE_RUN = "run"
MUTE_ALWAYS = "always"

#: Quiet time after the last invalidation before re-evaluating, ms.
DEBOUNCE_MS = 350

#: Bytes per GB, as the disk check counts them.
BYTES_PER_GB = 1e9

#: Free space under which the disk check warns, GB.
MIN_FREE_GB = 5.0

#: Columns never counted as a step's setting: its identity, the electrodes
#: and routes the empty-step check reads itself, and the voltage and
#: frequency, whose defaults follow the session's last values.
NON_SETTING_COLUMN_IDS = (
    "id",
    "name",
    "type",
    ELECTRODES_COL_ID,
    ROUTES_COL_ID,
    VOLTAGE_COLUMN_ID,
    FREQUENCY_COLUMN_ID,
)


def unused_column_check_id(column_id):
    """The check id of column ``column_id``'s unused check."""
    return f"{UNUSED_COLUMN_PREFIX}:{column_id}"


def ack_wait_off_check_id(column_id):
    """The check id of column ``column_id``'s ack-wait check."""
    return f"{ACK_WAIT_OFF_PREFIX}:{column_id}"


def run_mute_key(check_id, detail):
    """The "this run" mute key of one finding: the check and what it points
    at, so muting the empty step 4 leaves the empty step 7 showing."""
    return f"{check_id}|{detail}"

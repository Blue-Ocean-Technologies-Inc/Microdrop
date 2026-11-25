# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Microdrop package imports.
from dropbot_controller.consts import (
    CHIP_INSERTED,
    DROPBOT_DISCONNECTED,
    SELF_TESTS_PROGRESS,
    SELF_TESTS_RESULTS,
)

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# Topics this plugin wants some actors to subscribe to:
ACTOR_TOPIC_DICT = {
    f"{PKG}_listener": [
        CHIP_INSERTED,
        DROPBOT_DISCONNECTED,
        SELF_TESTS_PROGRESS,
        SELF_TESTS_RESULTS,
    ],
}

# ---------------------------------------------------------------------------
# Self-test reminder (Needs attention)
# ---------------------------------------------------------------------------
#: A full self-test run older than this many days is stale. A constant for
#: now; a preference can replace it.
SELF_TEST_STALE_DAYS = 10

#: The reminder's card: one thread, updated in place (never run, stale,
#: gone), and one condition, resolved the moment a full run completes.
SELF_TEST_REMINDER_THREAD_ID = f"{PKG}.self_test_reminder"
SELF_TEST_REMINDER_CONDITION_ID = f"{PKG}.self_test_needed"

#: The tutorial its help link names.
SELF_TEST_HELP_TARGET = "DropBot self tests"

#: When the last full run completed, in the notifications data folder
#: (``notifications.consts.notifications_data_dir``); written only by this
#: plugin, the moment a run completes. One value for any board: the
#: frontend has no stable id for the connected DropBot.
SELF_TEST_STATE_FILENAME = "self_test.json"
SELF_TEST_LAST_RUN_KEY = "last_full_run_completed"

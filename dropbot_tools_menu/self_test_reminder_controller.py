# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Posts the self-test reminder to the notifications drawer: a Needs
attention card while the full self test has never been run or its last run
is old, updated in place, and resolved the moment a full run completes.
Always quietly (no toast, no sound): it is posted at every launch. The time
of the last completed full run is kept in ``self_test.json`` in the
notifications data folder. Publishing is harmless without the
notifications plugin: nothing subscribes."""

# Standard library imports.
from datetime import date, datetime

# Enthought library imports.
from pyface.timer.api import CallbackTimer
from traits.api import Any, Bool, HasTraits, Int, Str

# Microdrop package imports.
from device_viewer.consts import DROPBOT_MAINTENANCE_CATEGORY_ID
from notifications.consts import (
    SEVERITY_WARNING,
    HelpAction,
    notification_publisher,
    notification_resolve_publisher,
    notifications_data_dir,
)

# Microdrop utils imports.
from microdrop_utils.json_state_file import read_json_state, write_json_state

# Local imports.
from .consts import (
    PKG,
    SELF_TEST_HELP_TARGET,
    SELF_TEST_LAST_RUN_KEY,
    SELF_TEST_REMINDER_CONDITION_ID,
    SELF_TEST_REMINDER_THREAD_ID,
    SELF_TEST_STATE_FILENAME,
)
from .self_test_reminder import (
    SELF_TEST_FRESH,
    is_full_run,
    reminder_state,
    reminder_text,
    session_resolution,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: How often (ms) the reminder looks again, so a run goes stale while the
#: app stays open.
RECHECK_INTERVAL_MS = 60 * 60 * 1000


class SelfTestReminderController(HasTraits):
    """Follows the self-test sessions and posts or resolves the reminder."""

    #: When the last full run completed, ISO; empty when never.
    last_run = Str()

    #: Whether the running session is the full suite, and how many of its
    #: tests reported failed channels so far.
    _full_session = Bool(False)
    _failed_tests = Int(0)

    #: The ``(state, age)`` last posted; None before the first look.
    _posted = Any()

    #: Looks again every RECHECK_INTERVAL_MS.
    _timer = Any()

    def start(self):
        """Read the last run and post the reminder; keep it current. Called
        once the launch is over (the window painted, deferred plugins in)."""
        data = read_json_state(self._state_path()) or {}
        self.last_run = str(data.get(SELF_TEST_LAST_RUN_KEY, ""))
        self.show_state()
        self._timer = CallbackTimer(
            interval=RECHECK_INTERVAL_MS / 1000, callback=self.show_state
        )
        self._timer.start()

    def stop(self):

        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    # ------------------------------------------------------------------ #
    # Sessions (from the self-test progress and results signals)          #
    # ------------------------------------------------------------------ #

    def session_started(self, tests):
        """A session of ``tests`` (names) started."""
        self._full_session = is_full_run(tests)
        self._failed_tests = 0

    def test_result(self, failed_channels):
        """A test of the session reported its results."""

        if failed_channels:
            self._failed_tests += 1

    def session_ended(self, status):
        """The session ended: a completed full run is the new last run, and
        clears the reminder."""
        full, self._full_session = self._full_session, False

        if not full or status != "completed":
            return

        self.last_run = datetime.now().isoformat(timespec="seconds")
        write_json_state(self._state_path(), {SELF_TEST_LAST_RUN_KEY: self.last_run})

        # A card posted this session (or at launch) clears; with none, the
        # resolve finds nothing.
        notification_resolve_publisher.publish(
            {
                "condition_id": SELF_TEST_REMINDER_CONDITION_ID,
                "resolution": session_resolution(self._failed_tests),
            }
        )
        self._posted = (SELF_TEST_FRESH, 0)

    # ------------------------------------------------------------------ #
    # The card                                                            #
    # ------------------------------------------------------------------ #

    def show_state(self):
        """Post or update the reminder for today's state; nothing when that
        state is the one already shown, or fresh."""
        state, age = reminder_state(self.last_run, date.today())

        if (state, age) == self._posted:
            return

        self._posted = (state, age)
        text = reminder_text(state, age)

        if text is None:
            return

        title, detail, priority = text
        logger.info(f"Self-test reminder: {title}")

        notification_publisher.publish(
            {
                "title": title,
                "detail": detail,
                "severity": SEVERITY_WARNING,
                "category": "hardware",
                "source": PKG,
                "secondary_action": HelpAction(
                    label="What does it check?", target=SELF_TEST_HELP_TARGET
                ),
                "needs_attention": True,
                "category_id": DROPBOT_MAINTENANCE_CATEGORY_ID,
                "thread_id": SELF_TEST_REMINDER_THREAD_ID,
                "condition_id": SELF_TEST_REMINDER_CONDITION_ID,
                "pop_up": False,
                "priority": priority,
            }
        )

    @staticmethod
    def _state_path():
        return notifications_data_dir() / SELF_TEST_STATE_FILENAME

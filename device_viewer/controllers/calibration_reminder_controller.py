# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Posts the calibration reminder to the notifications drawer: a Needs
attention card while no calibration is saved or the saved one is old,
updated in place as that changes, and resolved the moment a calibration is
measured. Always quietly (no toast, no sound): it is posted at every launch,
and nothing about it is news. Publishing is harmless without the
notifications plugin: nothing subscribes."""

# Standard library imports.
from datetime import date

# Enthought library imports.
from pyface.timer.api import CallbackTimer
from traits.api import Any, HasTraits, Instance, observe

# Microdrop package imports.
from dropbot_status_and_controls.consts import (
    CALIBRATION_TUTORIAL_ANCHOR,
    DROPBOT_STATUS_TUTORIAL_ID,
)
from notifications.consts import (
    SEVERITY_WARNING,
    HelpAction,
    help_target,
    notification_publisher,
    notification_resolve_publisher,
)

# Local imports.
from ..consts import (
    CALIBRATION_REMINDER_CONDITION_ID,
    CALIBRATION_REMINDER_THREAD_ID,
    DROPBOT_MAINTENANCE_CATEGORY_ID,
    PKG,
)
from ..models.calibration import CalibrationModel
from ..models.calibration_reminder import (
    CALIBRATED_RESOLUTION,
    CALIBRATION_FRESH,
    reminder_state,
    reminder_text,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: How often (ms) the reminder looks again, so a calibration goes stale
#: while the app stays open (at midnight, give or take an hour).
RECHECK_INTERVAL_MS = 60 * 60 * 1000


class CalibrationReminderController(HasTraits):
    """Follows the calibration and posts or resolves its reminder."""

    #: The calibration: its values and the day they were measured.
    calibration = Instance(CalibrationModel)

    #: The ``(state, age)`` last posted; None before the first look.
    _posted = Any()

    #: Looks again every RECHECK_INTERVAL_MS.
    _timer = Any()

    def start(self):
        """Post the reminder for the calibration as it is now, and keep it
        current. Called once its data has loaded, after the window has
        painted."""
        self.show_state()
        self._timer = CallbackTimer(
            interval=RECHECK_INTERVAL_MS / 1000, callback=self.show_state
        )
        self._timer.start()

    def stop(self):

        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    @observe(
        "calibration:[liquid_capacitance_over_area, filler_capacitance_over_area, "
        "calibrated_on]"
    )
    def _calibration_changed(self, event):

        # Before start() (the values loading), the first look is start's.
        if self._posted is not None:
            self.show_state()

    def show_state(self):
        """Post, update or resolve the reminder for today's state; nothing
        when that state is the one already shown."""
        calibration = self.calibration
        state, age = reminder_state(
            calibration.liquid_capacitance_over_area,
            calibration.filler_capacitance_over_area,
            calibration.calibrated_on,
            date.today(),
        )

        if (state, age) == self._posted:
            return

        shown_before = self._posted is not None and self._posted[0] != CALIBRATION_FRESH
        self._posted = (state, age)

        if state == CALIBRATION_FRESH:
            # Nothing to resolve at launch: no card was posted.
            if shown_before:
                notification_resolve_publisher.publish(
                    {
                        "condition_id": CALIBRATION_REMINDER_CONDITION_ID,
                        "resolution": CALIBRATED_RESOLUTION,
                    }
                )

            return

        title, detail, priority = reminder_text(state, age)
        logger.info(f"Calibration reminder: {title}")

        notification_publisher.publish(
            {
                "title": title,
                "detail": detail,
                "severity": SEVERITY_WARNING,
                "category": "hardware",
                "source": PKG,
                "secondary_action": HelpAction(
                    label="How to calibrate",
                    target=help_target(
                        DROPBOT_STATUS_TUTORIAL_ID, CALIBRATION_TUTORIAL_ANCHOR
                    ),
                ),
                "needs_attention": True,
                "category_id": DROPBOT_MAINTENANCE_CATEGORY_ID,
                "thread_id": CALIBRATION_REMINDER_THREAD_ID,
                "condition_id": CALIBRATION_REMINDER_CONDITION_ID,
                "pop_up": False,
                "priority": priority,
            }
        )

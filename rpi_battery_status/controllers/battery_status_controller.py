# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Poll the daemon's status file into the battery model."""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from pyface.timer.api import Timer
from traits.api import Callable, HasTraits, Instance

# Local imports.
from ..consts import POLL_INTERVAL_MS
from ..models.battery_status import BatteryStatus
from ..services.status_file_reader import read_snapshot, status_file_path


class BatteryStatusController(HasTraits):
    """Keep a BatteryStatus current from the daemon's status file.

    The pyface timer fires on the GUI thread, so observers of the model may
    drive widgets directly. Tests call ``poll()`` with a fake clock and never
    start the timer.
    """

    #: The battery state this controller keeps current.
    model = Instance(BatteryStatus, ())

    #: The daemon's status file.
    path = Instance(Path)

    #: Returns the current unix time (s); injectable for tests.
    clock = Callable(time.time)

    #: The polling timer while started; None while stopped.
    _timer = Instance(Timer)

    def _path_default(self):
        return status_file_path()

    def poll(self):
        """Refresh the model from the status file once."""
        snapshot = read_snapshot(self.path)

        if snapshot is None:
            self.model.mark_unavailable()
        else:
            self.model.apply_snapshot(snapshot, self.clock())

    def start(self):
        """Poll now, then every POLL_INTERVAL_MS until stopped."""
        self.poll()

        # A pyface Timer starts running as it is created.
        if self._timer is None:
            self._timer = Timer(POLL_INTERVAL_MS, self.poll)

    def stop(self):
        """Stop polling; the model keeps its last state."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Replay a real MicroDrop log's warnings and errors into the notifications,
a whole session compressed into REPLAY_SECONDS.

Reads a local file at run time and stores nothing; what it shows is the log
as written, unscrubbed.
"""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from pyface.timer.api import Timer
from traits.api import Any, Float, HasTraits, Int, List

# Local imports.
from .log_records import log_record, parse_log_text

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: How long a whole session takes to replay.
REPLAY_SECONDS = 20.0

#: How often the replay hands the due records over, in milliseconds.
REPLAY_TICK_MS = 100


class LogReplay(HasTraits):
    """Feeds a log's WARNING+ records to a logging handler over time."""

    #: The logging handler records go to, e.g. a NotificationLogHandler.
    handler = Any()

    #: The records, oldest first.
    records = List()

    #: How long the replay takes, in seconds.
    duration_s = Float(REPLAY_SECONDS)

    #: Records handed over so far.
    _sent = Int(0)

    #: When the replay started (time.monotonic).
    _started = Float()

    #: The running timer.
    _timer = Any()

    def start(self):
        """Start handing records over; returns self."""
        self._started = time.monotonic()
        self._timer = Timer(REPLAY_TICK_MS, self._tick)

        return self

    def _tick(self):
        if not self.records:
            self._timer.Stop()

            return

        first = self.records[0].created
        span = max(self.records[-1].created - first, 1e-6)
        elapsed = (time.monotonic() - self._started) / self.duration_s
        now = time.time()

        while self._sent < len(self.records):
            logged = self.records[self._sent]

            if (logged.created - first) / span > elapsed:
                break

            self.handler.handle(log_record(logged, created=now))
            self._sent += 1

        if self._sent >= len(self.records):
            self._timer.Stop()
            logger.info(f"Replayed {self._sent} log records")


def start_log_replay(path, handler):
    """Replay the log at ``path`` into ``handler``; the running LogReplay."""
    records = parse_log_text(Path(path).read_text(encoding="utf-8", errors="replace"))
    logger.info(f"Replaying {len(records)} warnings and errors from {path}")

    return LogReplay(handler=handler, records=records).start()

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Real MicroDrop log records, read back from a log file or the demo's
curated samples, as ``logging.LogRecord``s for the notifications' own log
handler. Qt-free.

A log line reads ``2026-08-05 16:09:10.123 [WARNING:device_viewer.x]:
message File "path", line 12``; the ``File …`` suffix is the file
formatter's, not the message's, so it is dropped, and the lines after a
record (a traceback) become its exception text, as the app's handler
would have seen them.
"""

# Standard library imports.
import datetime
import logging
import re
from typing import NamedTuple

#: One record's first line.
LOG_LINE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[.,](?P<ms>\d{1,6}) "
    r"\[(?P<level>[A-Z]+):(?P<name>[^\]]+)\]: (?P<message>.*)$"
)

#: The file formatter's ` File "…", line N` suffix.
FORMATTER_SUFFIX = re.compile(r'\s*File "[^"]*", line \d+\s*$')

#: Colour codes a console formatter may have left in a line.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


class LoggedRecord(NamedTuple):
    """One record as a log file has it."""

    created: float
    levelno: int
    name: str
    message: str
    traceback: str


def parse_log_text(text, min_level=logging.WARNING):
    """The records of a MicroDrop log at ``min_level`` or above, oldest
    first; lines before the first record are skipped."""
    records = []
    current = None

    for raw in text.splitlines():
        line = ANSI_ESCAPE.sub("", raw)
        match = LOG_LINE.match(line)

        if match is None:
            if current is not None:
                current["extra"].append(line)

            continue

        if current is not None:
            records.append(current)

        moment = datetime.datetime.strptime(match["time"], "%Y-%m-%d %H:%M:%S")
        current = {
            "created": moment.timestamp() + int(match["ms"]) / 10 ** len(match["ms"]),
            "levelno": logging.getLevelName(match["level"]),
            "name": match["name"],
            "message": match["message"],
            "extra": [],
        }

    if current is not None:
        records.append(current)

    return [
        _logged_record(record)
        for record in records
        if isinstance(record["levelno"], int) and record["levelno"] >= min_level
    ]


def _logged_record(record):
    """Split a parsed record's text into its message and traceback."""
    extra = "\n".join(record["extra"]).rstrip()
    extra = FORMATTER_SUFFIX.sub("", extra).rstrip()
    message = FORMATTER_SUFFIX.sub("", record["message"])
    traceback = ""

    if extra.lstrip().startswith("Traceback"):
        traceback = extra.strip()

    elif extra:
        # A message running over several lines, a traceback maybe inside.
        message = f"{message}\n{extra}"

    return LoggedRecord(
        record["created"], record["levelno"], record["name"], message, traceback
    )


def log_record(logged, created=None):
    """A ``logging.LogRecord`` for ``logged``, created at ``created`` (its
    own time if None), as the app's handlers would have received it."""
    record = logging.LogRecord(
        logged.name, logged.levelno, "", 0, logged.message, None, None
    )
    record.created = logged.created if created is None else created
    record.exc_text = logged.traceback or None

    return record

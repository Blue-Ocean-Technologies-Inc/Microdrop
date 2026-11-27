# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Forward warning and error log records to the notifications, in batches.

Records arrive on any thread. ``emit`` only snapshots the record into a
bounded buffer and, for the first record of a batch, schedules a delivery on
the GUI thread ``LOG_FLUSH_INTERVAL_MS`` later; the delivery collapses the
batch by key, so a burst of thousands of identical records is one update of
one entry, and posts it a chunk per GUI turn, so a burst of distinct ones
never holds the event loop for long.

Nothing on this path logs: a record from inside it would come straight back
here. ``emit`` also refuses records raised while it runs on the same thread,
and the plugin's own loggers are never forwarded.
"""

# Standard library imports.
import logging
import re
import sys
import threading
import traceback
from collections import deque

# Enthought library imports.
from pyface.api import GUI

# Local imports.
from ..consts import (
    CATEGORY_ID_LOG,
    CATEGORY_LOG,
    LOG_BUFFER_LIMIT,
    LOG_CHUNK_PAUSE_MS,
    LOG_DELIVERY_CHUNK,
    LOG_FLUSH_INTERVAL_MS,
    LOG_IGNORE_RULES,
    LOG_MIN_LEVEL,
    LOG_RECORDED_ATTR,
    LOG_TRAITS_LOGGER_NAME,
    MAX_ENTRIES,
    PKG,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
)
from ..models.notification_center import title_and_detail

#: Colour codes the console formatter writes into a record's name and level.
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

#: Formats a record's exception when no other handler has yet.
_EXCEPTION_FORMATTER = logging.Formatter()


def compile_ignore_rules(rules):
    """``(logger name, regex)`` pairs with their regexes compiled."""
    return [(name, re.compile(pattern)) for name, pattern in rules]


def is_ignored(logger_name, message, rules):
    """Whether a compiled rule covers ``logger_name`` (or a parent) and
    matches the start of ``message``."""

    for name, pattern in rules:
        covers = logger_name == name or logger_name.startswith(f"{name}.")

        if covers and pattern.match(message):
            return True

    return False


def snapshot_record(record):
    """The parts of ``record`` a notification needs, as a plain dict.

    Taken in ``emit``: other handlers rewrite the record afterwards (the
    console formatter colours its name), and the record may be reused.
    """
    name = ANSI_ESCAPE_PATTERN.sub("", record.name)
    message = ANSI_ESCAPE_PATTERN.sub("", record.getMessage())
    traceback_text = record.exc_text or ""

    if not traceback_text and record.exc_info:
        traceback_text = _EXCEPTION_FORMATTER.formatException(record.exc_info)

    if record.stack_info:
        traceback_text = f"{traceback_text}\n{record.stack_info}".strip()

    exception = record.exc_info[1] if record.exc_info else None

    # The exception's own line tells apart errors logged from one call site.
    # Read off the exception itself where there is one: a traceback can end
    # in a multi-line message's last line, in notes or in the stack.
    if exception is None:
        exception_line = traceback_text.strip().rsplit("\n", 1)[-1]

    else:
        first_line = str(exception).strip().partition("\n")[0]
        exception_line = type(exception).__name__

        if first_line:
            exception_line = f"{exception_line}: {first_line}"

    return {
        "name": name,
        "levelno": record.levelno,
        "message": message,
        "traceback": traceback_text,
        "created": record.created,
        "exception_line": exception_line,
        "key": (CATEGORY_LOG, name, record.levelno, str(record.msg), exception_line),
    }


def collapse_snapshots(snapshots, collapsed=None):
    """Collapse snapshots by key into ``collapsed`` (a new dict if None),
    oldest first: per key the latest snapshot, the first time and the count.

    Only the newest MAX_ENTRIES are kept: more distinct records would push
    the older ones out of the list anyway.
    """
    collapsed = {} if collapsed is None else collapsed

    for snapshot in snapshots:
        item = collapsed.pop(snapshot["key"], None)
        first_seen = snapshot["created"] if item is None else item["first_seen"]
        count = 1 if item is None else item["count"] + 1

        # Re-inserted, so the dict stays ordered by latest occurrence.
        collapsed[snapshot["key"]] = {
            "snapshot": snapshot,
            "first_seen": first_seen,
            "count": count,
        }

    for key in list(collapsed)[:-MAX_ENTRIES]:
        del collapsed[key]

    return collapsed


def post_arguments(item):
    """``NotificationCenter.post`` keywords for a collapsed item."""
    snapshot = item["snapshot"]
    text, detail = snapshot["message"], snapshot["traceback"]

    # The event description traits logs says nothing of what went wrong.
    if snapshot["name"] == LOG_TRAITS_LOGGER_NAME and snapshot["exception_line"]:
        text, detail = snapshot["exception_line"], f"{text}\n\n{detail}"

    title, detail = title_and_detail(text, detail)
    severity = (
        SEVERITY_ERROR if snapshot["levelno"] >= logging.ERROR else SEVERITY_WARNING
    )

    return {
        "title": title,
        "detail": detail,
        "severity": severity,
        "category": CATEGORY_LOG,
        "category_id": CATEGORY_ID_LOG,
        "source": snapshot["name"],
        "timestamp": snapshot["created"],
        "key": snapshot["key"],
        "first_seen": item["first_seen"],
        "count": item["count"],
    }


class NotificationLogHandler(logging.Handler):
    """A root-logger handler posting records to a NotificationCenter."""

    def __init__(
        self,
        center,
        level=LOG_MIN_LEVEL,
        ignore_rules=LOG_IGNORE_RULES,
        flush_interval_ms=LOG_FLUSH_INTERVAL_MS,
        buffer_limit=LOG_BUFFER_LIMIT,
        invoke_after=GUI.invoke_after,
    ):
        super().__init__(level)

        self.center = center
        self.flush_interval_ms = flush_interval_ms

        #: ``invoke_after(milliseconds, callable)`` on the GUI thread; any
        #: thread may call it.
        self._invoke_after = invoke_after

        self._ignore_rules = compile_ignore_rules([(PKG, ".*"), *ignore_rules])

        #: Snapshots waiting for delivery; the oldest drop past the limit.
        self._buffer = deque(maxlen=buffer_limit)

        #: Guards the buffer swap and the scheduled flag together.
        self._buffer_lock = threading.Lock()
        self._delivery_scheduled = False

        #: Per thread: True while ``emit`` runs, to refuse re-entry.
        self._emitting = threading.local()

        #: Collapsed records not posted yet, oldest first. GUI thread only.
        self._pending = {}
        self._chunk_scheduled = False

    def emit(self, record):
        """Snapshot ``record`` and make sure a delivery is scheduled."""

        if getattr(self._emitting, "active", False):
            return

        self._emitting.active = True

        try:
            self._buffer_record(record)

        # logging's own error path: it prints to stderr and never logs.
        except Exception:
            self.handleError(record)

        finally:
            self._emitting.active = False

    def deliver_buffered(self):
        """Collapse the buffered records into the pending ones and post the
        first chunk of them. GUI thread only."""

        with self._buffer_lock:
            snapshots = list(self._buffer)
            self._buffer.clear()
            self._delivery_scheduled = False

        collapse_snapshots(snapshots, self._pending)
        self._post_pending_chunk()

    def _post_pending_chunk(self):
        """Post the oldest LOG_DELIVERY_CHUNK pending items, then leave the
        event loop a pause before the next chunk: a flood of distinct
        records is listed over several turns instead of freezing one."""
        self._chunk_scheduled = False
        keys = list(self._pending)[:LOG_DELIVERY_CHUNK]

        try:
            for key in keys:
                self.center.post(**post_arguments(self._pending.pop(key)))

        # Logged, the failure would come back here and fail again on every
        # delivery; stderr, as logging reports its own handler errors.
        except Exception:
            self._pending.clear()
            traceback.print_exc(file=sys.stderr)

        if self._pending and not self._chunk_scheduled:
            self._chunk_scheduled = True
            self._invoke_after(LOG_CHUNK_PAUSE_MS, self._post_pending_chunk)

    def _buffer_record(self, record):

        # Its event is listed already, e.g. by the dialog shown for it.
        if getattr(record, LOG_RECORDED_ATTR, False):
            return

        snapshot = snapshot_record(record)

        if is_ignored(snapshot["name"], snapshot["message"], self._ignore_rules):
            return

        with self._buffer_lock:
            self._buffer.append(snapshot)
            schedule = not self._delivery_scheduled
            self._delivery_scheduled = True

        if schedule:
            self._invoke_after(self.flush_interval_ms, self.deliver_buffered)

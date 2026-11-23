# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The session's notifications, newest first. Qt-free; mutated on the GUI
thread only — posters on other threads hand over with ``GUI.invoke_later``.

A notification whose key matches an entry already listed collapses into it:
the count goes up, the text and time follow the latest occurrence, and the
entry moves to the top, unread again. Past ``max_entries`` the oldest entry
is dropped.
"""

# Standard library imports.
import time

# Enthought library imports.
from traits.api import Dict, HasTraits, Instance, Int, List, Property, Str

# Local imports.
from ..consts import (
    CATEGORY_GENERAL,
    MAX_ENTRIES,
    SEVERITIES,
    SEVERITY_INFO,
    TITLE_MAX_CHARS,
)
from .notification import Notification


def title_and_detail(text, detail=""):
    """Split ``text`` into a one-line title and the detail to show for it.

    The title is the first line, cut to TITLE_MAX_CHARS; the detail keeps
    the full text whenever the title does not, followed by ``detail``.
    """
    lines = text.strip().splitlines() or [""]
    title = lines[0]

    if len(title) > TITLE_MAX_CHARS:
        title = f"{title[: TITLE_MAX_CHARS - 1]}…"

    parts = []

    if len(lines) > 1 or title != lines[0]:
        parts.append(text.strip())

    if detail:
        parts.append(detail.strip())

    return title, "\n\n".join(parts)


class NotificationCenter(HasTraits):
    """The listed notifications and their unread state."""

    #: SOURCE OF TRUTH — the entries, newest first.
    entries = List(Instance(Notification))

    #: Entries kept; posting past it drops the oldest.
    max_entries = Int(MAX_ENTRIES)

    #: Entries not seen yet. An entry's severity never changes (it is part
    #: of its key), so only the unread flags are watched.
    unread_count = Property(Int, observe="entries.items.unread")

    #: The most urgent severity among the unread entries; "" when none.
    unread_severity = Property(Str, observe="entries.items.unread")

    #: Each listed entry by its key.
    _entries_by_key = Dict()

    def _get_unread_count(self):
        return sum(entry.unread for entry in self.entries)

    def _get_unread_severity(self):
        unread = [
            SEVERITIES.index(entry.severity) for entry in self.entries if entry.unread
        ]

        return SEVERITIES[max(unread)] if unread else ""

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def post(
        self,
        title,
        detail="",
        severity=SEVERITY_INFO,
        category=CATEGORY_GENERAL,
        source="",
        timestamp=None,
        action=None,
        key=None,
        count=1,
        first_seen=None,
    ):
        """List a notification, collapsing it into an equal-keyed entry.

        ``key`` defaults to ``(source, category, severity, title)``; ``count``
        and ``first_seen`` let a caller post several occurrences at once.

        Returns
        -------
        Notification
            The new or updated entry.
        """
        timestamp = time.time() if timestamp is None else timestamp
        key = (source, category, severity, title) if key is None else key
        entry = self._entries_by_key.get(key)

        if entry is not None:
            entry.trait_set(
                title=title,
                detail=detail or entry.detail,
                action=action or entry.action,
                count=entry.count + count,
                last_seen=timestamp,
                unread=True,
            )
            self._move_to_top(entry)

            return entry

        entry = Notification(
            key=key,
            title=title,
            detail=detail,
            severity=severity,
            category=category,
            source=source,
            first_seen=timestamp if first_seen is None else first_seen,
            last_seen=timestamp,
            action=action,
            count=count,
        )
        self._entries_by_key[key] = entry
        self.entries.insert(0, entry)
        self._drop_oldest()

        return entry

    def post_message(self, message):
        """List a validated ``NotificationMessage``."""
        title, detail = title_and_detail(message.title, message.detail)

        return self.post(
            title,
            detail=detail,
            severity=message.severity,
            category=message.category,
            source=message.source,
            timestamp=message.timestamp,
            action=message.action,
        )

    def find(self, key):
        """The listed entry with ``key``, or None."""
        return self._entries_by_key.get(key)

    def mark_all_read(self):
        """Mark every entry seen."""
        for entry in self.entries:
            entry.unread = False

    def dismiss(self, entry):
        """Drop one entry."""

        if entry not in self.entries:
            return

        self.entries.remove(entry)
        self._entries_by_key.pop(entry.key, None)

    def clear(self):
        """Drop every entry."""
        self._entries_by_key = {}
        self.entries = []

    # ------------------------------------------------------------------ #
    # Private interface                                                   #
    # ------------------------------------------------------------------ #

    def _move_to_top(self, entry):
        if self.entries[0] is entry:
            return

        self.entries.remove(entry)
        self.entries.insert(0, entry)

    def _drop_oldest(self):
        while len(self.entries) > self.max_entries:
            dropped = self.entries.pop()
            self._entries_by_key.pop(dropped.key, None)

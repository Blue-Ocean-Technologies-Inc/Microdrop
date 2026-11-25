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
entry moves to the top, unread again. Posts naming a thread update that
thread's one entry in place instead. Past ``max_entries`` the oldest entry
is dropped.

The counts are plain traits kept current here, not Properties: observers of
a Property that changes again while its change is announced can be left
holding the stale value (#1134). Many entries change in one go through
``update_all``, which recounts once (#1136).
"""

# Standard library imports.
import time

# Enthought library imports.
from traits.api import (
    Dict,
    Event,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
    observe,
)

# Local imports.
from ..consts import (
    CATEGORY_GENERAL,
    MAX_ENTRIES,
    SEVERITIES,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    TITLE_MAX_CHARS,
)
from .notification import THREAD_KEY, Notification
from .settings import NotificationSettings


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
    """The listed notifications, their counts and their arrivals."""

    #: SOURCE OF TRUTH — the entries, newest first.
    entries = List(Instance(Notification))

    #: Entries kept; posting past it drops the oldest.
    max_entries = Int(MAX_ENTRIES)

    #: The user's choices per category: one kept out of the drawer is not
    #: recorded at all, unless it is an error or needs attention.
    settings = Instance(NotificationSettings, ())

    #: Entries not seen yet, and the most urgent severity among them ("" when
    #: none); entries marked new in the open drawer.
    unread_count = Int(0)
    unread_severity = Str()
    new_count = Int(0)

    #: Fired with an entry that is new, or unread again after being read:
    #: what deserves a toast.
    arrived = Event(Instance(Notification))

    #: Fired with an unread entry another occurrence collapsed into.
    repeated = Event(Instance(Notification))

    #: Fired after ``update_all`` changed many entries quietly.
    bulk_changed = Event()

    #: Entries the user has to act on, highest priority then newest first;
    #: and every other entry, newest first.
    attention_entries = Property(
        List(Instance(Notification)),
        observe="entries.items.[needs_attention, priority]",
    )
    history_entries = Property(
        List(Instance(Notification)), observe="entries.items.needs_attention"
    )

    #: Each listed entry by its key.
    _entries_by_key = Dict()

    def _get_attention_entries(self):
        attention = [entry for entry in self.entries if entry.needs_attention]

        # Stable: equal priorities keep their newest-first order.
        return sorted(attention, key=lambda entry: -entry.priority)

    def _get_history_entries(self):
        return [entry for entry in self.entries if not entry.needs_attention]

    # ------------------------------------------------------------------ #
    # Posting                                                             #
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
        secondary_action=None,
        needs_attention=False,
        condition_id="",
        category_id="",
        thread_id="",
        pop_up=True,
        priority=0,
    ):
        """List a notification, collapsing it into an equal-keyed entry, or
        updating its thread's entry in place.

        ``key`` defaults to ``(source, category, severity, title)``; ``count``
        and ``first_seen`` let a caller post several occurrences at once.

        Returns
        -------
        Notification or None
            The new or updated entry; None when its category is kept out of
            the drawer.
        """

        if not self._kept(severity, needs_attention, category_id):
            return None

        timestamp = time.time() if timestamp is None else timestamp

        if thread_id:
            key = (THREAD_KEY, thread_id)

        elif key is None:
            key = (source, category, severity, title)

        state = {
            "detail": detail,
            "action": action,
            "secondary_action": secondary_action,
            "needs_attention": needs_attention,
            "condition_id": condition_id,
            "category_id": category_id,
            "pop_up": pop_up,
            "priority": priority,
        }
        entry = self._entries_by_key.get(key)

        if entry is None:
            entry = Notification(
                key=key,
                title=title,
                severity=severity,
                category=category,
                source=source,
                first_seen=timestamp if first_seen is None else first_seen,
                last_seen=timestamp,
                count=count,
                **state,
            )

            return self._add(entry)

        return self._update(entry, title, severity, timestamp, count, state, thread_id)

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
            secondary_action=message.secondary_action,
            needs_attention=message.needs_attention,
            condition_id=message.condition_id,
            category_id=message.category_id,
            thread_id=message.thread_id,
            pop_up=message.pop_up,
            priority=message.priority,
        )

    def find(self, key):
        """The listed entry with ``key``, or None."""
        return self._entries_by_key.get(key)

    # ------------------------------------------------------------------ #
    # Changing entries                                                    #
    # ------------------------------------------------------------------ #

    def resolve(self, condition_id, resolution):
        """The condition ``condition_id`` cleared: its cards leave Needs
        attention, read, their buttons replaced by ``resolution``."""
        cleared = [
            entry
            for entry in self.attention_entries
            if entry.condition_id == condition_id
        ]

        for entry in cleared:
            entry.trait_set(needs_attention=False, unread=False, acted=resolution)

    def update_all(self, entries, **traits):
        """Set ``traits`` on ``entries`` quietly, then recount and announce
        it once, as ``bulk_changed``: each change announced on its own made
        every count recompute over every entry (#1136). Each card still
        follows its own entry's ``changed``."""
        entries = list(entries)

        if not entries:
            return

        for entry in entries:
            entry.trait_setq(**traits)

        self._recount()
        self.bulk_changed = True

        for entry in entries:
            entry.changed = True

    def mark_all_read(self):
        """Mark every entry seen, in one change."""
        self.update_all([entry for entry in self.entries if entry.unread], unread=False)

    def dismiss(self, entry):
        """Drop one entry."""

        if entry not in self.entries:
            return

        self.entries.remove(entry)
        self._entries_by_key.pop(entry.key, None)

    def clear(self):
        """Drop every entry except those still needing attention."""
        kept = self.attention_entries

        self._entries_by_key = {entry.key: entry for entry in kept}
        self.entries = kept

    def clear_everything(self):
        """Drop every entry, Needs attention too."""
        self._entries_by_key = {}
        self.entries = []

    # ------------------------------------------------------------------ #
    # Counts                                                              #
    # ------------------------------------------------------------------ #

    @observe("entries.items")
    @observe("entries:items:[unread, is_new]")
    def _follow_entries(self, event):
        self._recount()

    def _recount(self):
        unread = [entry for entry in self.entries if entry.unread]
        levels = [SEVERITIES.index(entry.severity) for entry in unread]

        self.trait_set(
            unread_count=len(unread),
            unread_severity=SEVERITIES[max(levels)] if levels else "",
            new_count=sum(entry.is_new for entry in self.entries),
        )

    # ------------------------------------------------------------------ #
    # Private interface                                                   #
    # ------------------------------------------------------------------ #

    def _kept(self, severity, needs_attention, category_id):
        kind = self.settings.category(category_id)

        if kind is None or kind.in_drawer:
            return True

        return severity == SEVERITY_ERROR or needs_attention

    def _add(self, entry):
        self._entries_by_key[entry.key] = entry
        self.entries.insert(0, entry)
        self._drop_oldest()
        self.arrived = entry

        return entry

    def _update(self, entry, title, severity, timestamp, count, state, thread_id):
        """Collapse a post into ``entry``; a thread's post replaces its state
        whole, counted once."""
        was_unread = entry.unread

        if thread_id:
            entry.trait_set(severity=severity, **state)

        else:
            entry.trait_set(
                detail=state["detail"] or entry.detail,
                action=state["action"] or entry.action,
                secondary_action=state["secondary_action"] or entry.secondary_action,
                needs_attention=state["needs_attention"] or entry.needs_attention,
                condition_id=state["condition_id"] or entry.condition_id,
                category_id=state["category_id"] or entry.category_id,
                pop_up=state["pop_up"],
                priority=max(state["priority"], entry.priority),
            )

        entry.trait_set(
            title=title,
            count=entry.count if thread_id else entry.count + count,
            last_seen=timestamp,
            acted="",
            unread=True,
        )
        self._move_to_top(entry)

        if was_unread:
            self.repeated = entry

        else:
            self.arrived = entry

        return entry

    def _move_to_top(self, entry):

        if self.entries[0] is entry:
            return

        self.entries.remove(entry)
        self.entries.insert(0, entry)

    def _drop_oldest(self):

        while len(self.entries) > self.max_entries:
            dropped = self.entries.pop()
            self._entries_by_key.pop(dropped.key, None)

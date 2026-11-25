# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's own sections, Qt-free: Needs attention at the top and
Activity at the bottom, both lists of notification cards, with Activity's
filters and day groups."""

# Standard library imports.
import time
from datetime import datetime, timedelta

# Enthought library imports.
from traits.api import Bool, Instance, Str, observe

# Microdrop style imports.
from microdrop_style.colors import SLATE
from microdrop_style.icons.icons import ICON_HISTORY

# Local imports.
from ..consts import (
    ATTENTION_SECTION_ID,
    HISTORY_SECTION_ID,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    NotificationSection,
)
from .notification_center import NotificationCenter

#: The sections' titles, kept short.
ATTENTION_SECTION_TITLE = "Needs attention"
HISTORY_SECTION_TITLE = "Activity"

#: Needs attention first, Activity last, contributed sections between.
ATTENTION_SECTION_ORDER = -100
HISTORY_SECTION_ORDER = 1000

#: Needs attention's accent by theme: a deep orange, darker on light and
#: lighter on dark so its glyph reads (WARNING_COLOR's yellow would not).
ATTENTION_ACCENT = ("#AC4E0C", "#F08A3C")

#: Activity's filters: every entry, the errors, or those with a button left
#: to press.
FILTER_ALL = "all"
FILTER_ERRORS = "errors"
FILTER_ACTION = "action"
FILTERS = (FILTER_ALL, FILTER_ERRORS, FILTER_ACTION)

#: Activity's day headings.
DAY_TODAY = "Today"
DAY_YESTERDAY = "Yesterday"
DAY_EARLIER = "Earlier"


def matches_filter(entry, name):
    """Whether ``entry`` shows under Activity's filter ``name``."""

    if name == FILTER_ERRORS:
        return entry.severity == SEVERITY_ERROR

    # A button still to press on a warning or an error: "Retry", not a
    # success's "Show folder".
    if name == FILTER_ACTION:
        urgent = entry.severity in (SEVERITY_WARNING, SEVERITY_ERROR)

        return urgent and entry.action is not None and not entry.acted

    return True


def filter_counts(entries):
    """How many of ``entries`` each filter shows."""
    return {
        name: sum(matches_filter(entry, name) for entry in entries) for name in FILTERS
    }


def time_group(seconds, now=None):
    """The day heading an entry goes under: Today, Yesterday or Earlier."""
    now = time.time() if now is None else now
    day = datetime.fromtimestamp(seconds).date()
    today = datetime.fromtimestamp(now).date()

    if day == today:
        return DAY_TODAY

    if day == today - timedelta(days=1):
        return DAY_YESTERDAY

    return DAY_EARLIER


class CardListSection(NotificationSection):
    """A drawer section listing notification cards. The drawer's column
    builds its cards; it needs no factory."""

    #: Whose entries it lists.
    center = Instance(NotificationCenter)

    #: Which entries: the centre's ``attention_entries`` or
    #: ``history_entries``.
    entries_name = Str()

    #: Whether the section shows at all; Needs attention hides when empty.
    available = Bool(True)

    def entries(self):
        """The entries listed, newest first."""
        return getattr(self.center, self.entries_name)


class AttentionSection(CardListSection):
    """The cards the user has to act on, at the top."""

    id = ATTENTION_SECTION_ID
    title = ATTENTION_SECTION_TITLE
    order = ATTENTION_SECTION_ORDER
    expanded = True
    entries_name = "attention_entries"
    glyph = "priority_high"
    accent = ATTENTION_ACCENT

    @observe("center.entries.items.needs_attention")
    @observe("center:bulk_changed")
    def _follow_entries(self, event):
        count = len(self.entries())

        self.summary = str(count) if count else ""
        self.available = bool(count)


class HistorySection(CardListSection):
    """Every other notification, filling the rest of the drawer."""

    id = HISTORY_SECTION_ID
    title = HISTORY_SECTION_TITLE
    order = HISTORY_SECTION_ORDER
    expanded = True
    entries_name = "history_entries"
    glyph = ICON_HISTORY
    accent = (SLATE["light"], SLATE["dark"])

    @observe("center.entries.items.needs_attention")
    @observe("center:new_count")
    def _follow_entries(self, event):
        entries = self.entries()
        total = len(entries)
        new = sum(entry.is_new for entry in entries)

        if new:
            self.summary = f"{new} new · {total}"

        else:
            self.summary = str(total) if total else ""

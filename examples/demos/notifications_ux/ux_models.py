# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the prototype: the product's notification, centre and
pane models, extended with a second button, Needs attention, the "new"
marker, the toasts on screen and the drawer's session layout.
"""

# Standard library imports.
import time
from datetime import datetime, timedelta

# Enthought library imports.
from traits.api import (
    Bool,
    Enum,
    Event,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
    Union,
    observe,
)

# Microdrop package imports.
from notifications.consts import (
    CATEGORY_GENERAL,
    SEVERITIES,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    NotificationSection,
)
from notifications.models.notification import Notification
from notifications.models.notification_center import (
    NotificationCenter,
    title_and_detail,
)
from notifications.models.notifications_pane_model import NotificationsPaneModel

# Local imports.
from .ux_consts import (
    ATTENTION_SECTION_ID,
    ATTENTION_SECTION_ORDER,
    ATTENTION_SECTION_TITLE,
    DRAWER_DEFAULT_WIDTH,
    FEED_SEVERITY,
    FILTER_ACTION,
    FILTER_ALL,
    FILTER_ERRORS,
    HISTORY_SECTION_ID,
    HISTORY_SECTION_ORDER,
    HISTORY_SECTION_TITLE,
    TOAST_TIMEOUT_MS,
    HelpAction,
    SnoozeAction,
)


class UxNotification(Notification):
    """A notification with a second button and a Needs attention flag."""

    #: The second, quieter button.
    secondary_action = Union(None, Instance(HelpAction), Instance(SnoozeAction))

    #: The user has to do something about it.
    needs_attention = Bool(False)

    #: Seen for the first time in the drawer open now; marked until it closes.
    is_new = Bool(False)

    #: What the user did with it, e.g. "Calibrate"; empty until then.
    acted = Str()

    #: For a new news post's stand-in: the post's id. Such an entry is
    #: never listed in the centre; it toasts and counts on the bell.
    feed_post_id = Str()

    #: The stand-in's news section, and its publisher's look.
    feed_section_id = Str()
    feed_accent = Str()
    feed_logo = Str()
    feed_monogram = Str()

    #: Whether it stays on screen as a toast until dismissed or acted on.
    sticky = Property(Bool, observe="severity, action, needs_attention")

    def _get_sticky(self):
        urgent = self.severity in (SEVERITY_WARNING, SEVERITY_ERROR)

        return urgent or self.needs_attention or self.action is not None

    @observe("secondary_action, needs_attention, is_new, acted")
    def _announce_ux_change(self, event):
        self.changed = True


class UxNotificationCenter(NotificationCenter):
    """The notifications; Needs attention entries survive Clear all."""

    #: Fired with an entry that is new, or unread again after being read:
    #: what deserves a toast.
    arrived = Event(Instance(Notification))

    #: Fired with an unread entry another occurrence collapsed into.
    repeated = Event(Instance(Notification))

    #: Fired after ``update_all`` changed many entries quietly: whatever
    #: counts unread or new entries counts again.
    bulk_changed = Event()

    #: Entries the user has to act on, newest first.
    attention_entries = Property(
        List(Instance(Notification)), observe="entries.items.needs_attention"
    )

    #: Every other entry, newest first.
    history_entries = Property(
        List(Instance(Notification)), observe="entries.items.needs_attention"
    )

    #: Entries marked new in the open drawer.
    new_count = Property(Int, observe="entries.items.is_new")

    def _get_attention_entries(self):
        return [entry for entry in self.entries if entry.needs_attention]

    def _get_history_entries(self):
        return [entry for entry in self.entries if not entry.needs_attention]

    def _get_new_count(self):
        return sum(entry.is_new for entry in self.entries)

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
    ):
        """List a notification as the product centre does, as an
        UxNotification, and announce it for a toast."""
        timestamp = time.time() if timestamp is None else timestamp
        key = (source, category, severity, title) if key is None else key
        entry = self._entries_by_key.get(key)

        if entry is not None:
            was_unread = entry.unread

            entry.trait_set(
                title=title,
                detail=detail or entry.detail,
                action=action or entry.action,
                secondary_action=secondary_action or entry.secondary_action,
                needs_attention=needs_attention or entry.needs_attention,
                count=entry.count + count,
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

        entry = UxNotification(
            key=key,
            title=title,
            detail=detail,
            severity=severity,
            category=category,
            source=source,
            first_seen=timestamp if first_seen is None else first_seen,
            last_seen=timestamp,
            action=action,
            secondary_action=secondary_action,
            needs_attention=needs_attention,
            count=count,
        )
        self._entries_by_key[key] = entry
        self.entries.insert(0, entry)
        self._drop_oldest()
        self.arrived = entry

        return entry

    def post_message(self, message):
        """List a validated NotificationMessage or UxNotificationMessage."""
        title, detail = title_and_detail(message.title, message.detail)

        return self.post(
            title,
            detail=detail,
            severity=message.severity,
            category=message.category,
            source=message.source,
            timestamp=message.timestamp,
            action=message.action,
            secondary_action=getattr(message, "secondary_action", None),
            needs_attention=getattr(message, "needs_attention", False),
        )

    def update_all(self, entries, **traits):
        """Set ``traits`` on ``entries`` quietly, then announce it once, as
        ``bulk_changed``: hundreds of entries, each telling every observer
        of the counts, made opening the drawer stall. Counts and summaries
        observe ``bulk_changed`` too; each card follows its entry's own
        ``changed``."""
        entries = list(entries)

        if not entries:
            return

        for entry in entries:
            entry.trait_setq(**traits)

        self.bulk_changed = True

        for entry in entries:
            entry.changed = True

    def mark_all_read(self):
        """Mark every entry seen, in one change."""
        self.update_all([entry for entry in self.entries if entry.unread], unread=False)

    def clear(self):
        """Drop every entry except those still needing attention."""
        kept = self.attention_entries

        self._entries_by_key = {entry.key: entry for entry in kept}
        self.entries = kept

    def clear_everything(self):
        """Drop every entry, Needs attention too."""
        super().clear()


class ToastSettings(HasTraits):
    """How toasts behave: the user's choice, a sketch of what a preferences
    helper would hold once ported."""

    #: Info and success toasts leave on their own; off, every toast stays
    #: until dismissed or acted on, and no countdown is drawn.
    auto_dismiss = Bool(True)

    #: Seconds an info or success toast stays, hover not counted.
    auto_dismiss_seconds = Int(TOAST_TIMEOUT_MS // 1000)

    #: ``auto_dismiss_seconds`` in milliseconds.
    timeout_ms = Property(Int, observe="auto_dismiss_seconds")

    def _get_timeout_ms(self):
        return self.auto_dismiss_seconds * 1000


class ToastItem(HasTraits):
    """One toast on screen."""

    #: The notification it shows.
    entry = Instance(Notification)

    #: Milliseconds left before it leaves on its own; sticky toasts keep it.
    remaining_ms = Int(TOAST_TIMEOUT_MS)

    #: While the pointer is over it, its time does not run.
    hovered = Bool(False)

    #: Set when it starts leaving; the view animates it out, then calls
    #: ``ToastStackModel.remove``.
    leaving = Bool(False)

    #: Where it goes when it leaves: into the bell (still unread), or simply
    #: away (acted on, dismissed from the list, or the drawer opened).
    into_bell = Bool(True)


class ToastStackModel(HasTraits):
    """The toasts on screen, oldest first, and the arrivals past the limit."""

    items = List(Instance(ToastItem))

    #: Whether and when toasts leave on their own.
    settings = Instance(ToastSettings, ())

    #: Toasts that did not fit, gone straight to the bell since the stack
    #: was last empty, oldest first; and how many.
    overflow_entries = List(Instance(Notification))
    overflow = Property(Int, observe="overflow_entries.items")

    #: SOURCE OF TRUTH for quiet mode: while True only errors and Needs
    #: attention items pop up; the rest are held for one summary toast when
    #: it ends. A protocol run sets it.
    quiet = Bool(False)

    #: What runs while quiet, for the summary: "Protocol finished · ...".
    quiet_reason = Str("Protocol")

    #: Entries held while quiet, oldest first.
    held = List(Instance(Notification))

    #: Entries on screen as toasts (leaving ones too, until they land).
    entries_shown = Property(List, observe="items.items")

    def _get_entries_shown(self):
        return [item.entry for item in self.items]

    def _get_overflow(self):
        return len(self.overflow_entries)

    def times_out(self, item):
        """Whether ``item`` leaves on its own: an info or success toast,
        while the settings say toasts time out."""
        return self.settings.auto_dismiss and not item.entry.sticky

    def progress(self, item):
        """``item``'s time left, 0-1; None when it does not time out."""

        if not self.times_out(item):
            return None

        return item.remaining_ms / max(self.settings.timeout_ms, 1)

    def find(self, entry):
        """The toast showing ``entry``, or None."""

        for item in self.items:
            if item.entry is entry:
                return item

        return None

    def remove(self, item):
        """Take a toast off, once it has left."""

        if item in self.items:
            self.items.remove(item)

        if not self.items:
            self.overflow_entries = []


class UxPaneModel(NotificationsPaneModel):
    """What the drawer, the toasts and the bell show."""

    center = Instance(UxNotificationCenter, ())

    #: The toasts on screen.
    toasts = Instance(ToastStackModel, ())

    #: The drawer's width (px), for the session.
    drawer_width = Int(DRAWER_DEFAULT_WIDTH)

    #: The bell's count: unread entries not on screen as toasts. A toast
    #: landing in the bell ticks it up.
    bell_count = Property(
        Int, observe="center.unread_count, toasts.items.items, feed_alerts.items.unread"
    )

    #: The most urgent severity counted on the bell; "" when none.
    bell_severity = Property(
        Str, observe="center.unread_count, toasts.items.items, feed_alerts.items.unread"
    )

    #: Fired with the entry whose second button the user pressed.
    run_secondary_action = Event(Instance(Notification))

    #: Stand-ins for new news posts, oldest first: unread until
    #: the feed has been seen in the open drawer, new until it closes.
    feed_alerts = List(Instance(Notification))

    #: Which Activity entries show.
    history_filter = Enum(FILTER_ALL, FILTER_ERRORS, FILTER_ACTION)

    #: Fired with an entry the open drawer scrolls to and highlights.
    reveal = Event(Instance(Notification))

    def reveal_entry(self, entry):
        """Open the drawer on ``entry``."""
        self.is_open = True
        self.reveal = entry

    def _bell_entries(self):
        shown = self.toasts.entries_shown
        entries = [*self.center.entries, *self.feed_alerts]

        return [entry for entry in entries if entry.unread and entry not in shown]

    def _get_bell_count(self):
        return len(self._bell_entries())

    def _get_bell_severity(self):
        """The most urgent severity counted; FEED_SEVERITY when only new
        feed posts are."""
        counted = self._bell_entries()
        levels = [
            SEVERITIES.index(entry.severity)
            for entry in counted
            if not entry.feed_post_id
        ]

        if levels:
            return SEVERITIES[max(levels)]

        return FEED_SEVERITY if counted else ""


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


def time_group(seconds, now=None):
    """The day heading an entry goes under: Today, Yesterday or Earlier."""
    now = time.time() if now is None else now
    day = datetime.fromtimestamp(seconds).date()
    today = datetime.fromtimestamp(now).date()

    if day == today:
        return "Today"

    if day == today - timedelta(days=1):
        return "Yesterday"

    return "Earlier"


class CardListSection(NotificationSection):
    """A drawer section listing notification cards: Needs attention or the
    rest. The drawer's column builds its cards; it needs no factory."""

    #: The drawer's model, whose centre lists the entries.
    pane_model = Instance(UxPaneModel)

    #: Which entries: the centre's ``attention_entries`` or
    #: ``history_entries``.
    entries_name = Str()

    #: Whether the section shows at all; Needs attention hides when empty.
    available = Bool(True)


class AttentionSection(CardListSection):
    """The cards the user has to act on, at the top."""

    id = ATTENTION_SECTION_ID
    title = ATTENTION_SECTION_TITLE
    order = ATTENTION_SECTION_ORDER
    expanded = True
    entries_name = "attention_entries"

    @observe("pane_model.center.entries.items.needs_attention")
    @observe("pane_model:center:bulk_changed")
    def _follow_entries(self, event):
        count = len(self.pane_model.center.attention_entries)

        self.summary = str(count) if count else ""
        self.available = bool(count)


class HistorySection(CardListSection):
    """Every other notification, filling the rest of the drawer."""

    id = HISTORY_SECTION_ID
    title = HISTORY_SECTION_TITLE
    order = HISTORY_SECTION_ORDER
    expanded = True
    entries_name = "history_entries"

    @observe("pane_model.center.entries.items.[needs_attention, is_new]")
    @observe("pane_model:center:bulk_changed")
    def _follow_entries(self, event):
        center = self.pane_model.center
        total = len(center.history_entries)
        new = sum(entry.is_new for entry in center.history_entries)

        if new:
            self.summary = f"{new} new · {total}"

        else:
            self.summary = str(total) if total else ""

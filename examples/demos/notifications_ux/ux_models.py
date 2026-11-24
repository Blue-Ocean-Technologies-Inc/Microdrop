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

# Enthought library imports.
from traits.api import (
    Bool,
    Dict,
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
    DRAWER_DEFAULT_WIDTH,
    HISTORY_SECTION_ID,
    HISTORY_SECTION_ORDER,
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

    def clear(self):
        """Drop every entry except those still needing attention."""
        kept = self.attention_entries

        self._entries_by_key = {entry.key: entry for entry in kept}
        self.entries = kept

    def clear_everything(self):
        """Drop every entry, Needs attention too."""
        super().clear()


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

    #: Toasts that did not fit, gone straight to the bell since the stack
    #: was last empty.
    overflow = Int(0)

    #: Entries on screen as toasts (leaving ones too, until they land).
    entries_shown = Property(List, observe="items.items")

    def _get_entries_shown(self):
        return [item.entry for item in self.items]

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
            self.overflow = 0


class UxPaneModel(NotificationsPaneModel):
    """What the drawer, the toasts and the bell show."""

    center = Instance(UxNotificationCenter, ())

    #: The toasts on screen.
    toasts = Instance(ToastStackModel, ())

    #: The drawer's width (px), for the session.
    drawer_width = Int(DRAWER_DEFAULT_WIDTH)

    #: Each resized section's contents height (px), by section id, for the
    #: session.
    section_heights = Dict(Str, Int)

    #: The bell's count: unread entries not on screen as toasts. A toast
    #: landing in the bell ticks it up.
    bell_count = Property(Int, observe="center.unread_count, toasts.items.items")

    #: The most urgent severity counted on the bell; "" when none.
    bell_severity = Property(Str, observe="center.unread_count, toasts.items.items")

    #: Fired with the entry whose second button the user pressed.
    run_secondary_action = Event(Instance(Notification))

    def _bell_entries(self):
        shown = self.toasts.entries_shown

        return [
            entry
            for entry in self.center.entries
            if entry.unread and entry not in shown
        ]

    def _get_bell_count(self):
        return len(self._bell_entries())

    def _get_bell_severity(self):
        levels = [SEVERITIES.index(entry.severity) for entry in self._bell_entries()]

        return SEVERITIES[max(levels)] if levels else ""


class CardListSection(NotificationSection):
    """A drawer section listing notification cards: Needs attention or the
    rest."""

    #: The drawer's model, whose centre lists the entries.
    pane_model = Instance(UxPaneModel)

    #: Which entries: the centre's ``attention_entries`` or
    #: ``history_entries``.
    entries_name = Str()

    #: Whether the section shows at all; Needs attention hides when empty.
    available = Bool(True)

    def _factory_default(self):
        return self.build_contents

    def build_contents(self, parent):
        """The cards, as a scrolled list."""
        from .card_list_view import CardListView

        return CardListView(self.pane_model, self.entries_name, parent)


class AttentionSection(CardListSection):
    """The cards the user has to act on, at the top."""

    id = ATTENTION_SECTION_ID
    title = "Needs attention"
    order = ATTENTION_SECTION_ORDER
    expanded = True
    entries_name = "attention_entries"

    @observe("pane_model.center.entries.items.needs_attention")
    def _follow_entries(self, event):
        count = len(self.pane_model.center.attention_entries)

        self.summary = str(count) if count else ""
        self.available = bool(count)


class HistorySection(CardListSection):
    """Every other notification, filling the rest of the drawer."""

    id = HISTORY_SECTION_ID
    title = "Notifications"
    order = HISTORY_SECTION_ORDER
    expanded = True
    entries_name = "history_entries"

    @observe("pane_model.center.entries.items.[needs_attention, is_new]")
    def _follow_entries(self, event):
        center = self.pane_model.center
        total = len(center.history_entries)
        new = sum(entry.is_new for entry in center.history_entries)

        if new:
            self.summary = f"{new} new · {total}"

        else:
            self.summary = str(total) if total else ""

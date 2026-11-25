# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the drawer, the toasts and the bell: the notifications,
the sections of the drawer's column, the user's requests on them, and what
the bell counts."""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Enum,
    Event,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
    Tuple,
    observe,
)

# Local imports.
from ..consts import DRAWER_WIDTH, SEVERITIES, SEVERITY_ERROR, NotificationSection
from .notification import Notification
from .notification_center import NotificationCenter
from .own_sections import ATTENTION_ACCENT, FILTERS
from .toasts import ToastStackModel

#: The bell's "severity" while it counts only section alerts (new posts):
#: below info, drawn in the newest alert's accent.
ALERT_SEVERITY = "alert"


def bell_summary(entries, shown):
    """What the bell shows: ``(count, severity, accent, attention, new)``.

    Needs attention entries are outstanding work: each counts until it is
    resolved, acted on or dismissed, read or not. Every other entry (a
    section's alert included, unless it is not ``counted``) counts while
    unread and not on screen as a toast (``shown``: their ids), so a toast
    landing in the bell adds to the count.

    The colour: red when an unread error counts; else the Needs attention
    orange (ALERT_SEVERITY with ATTENTION_ACCENT) while anything needs
    attention; else the worst unread severity; else the last section
    alert's accent; "" when nothing counts.
    """
    attention = [entry for entry in entries if entry.needs_attention]
    new = [
        entry
        for entry in entries
        if not entry.needs_attention
        and entry.unread
        and id(entry) not in shown
        and getattr(entry.alert, "counted", True)
    ]
    unread_errors = [
        entry
        for entry in [*attention, *new]
        if entry.unread and entry.severity == SEVERITY_ERROR and not entry.section_id
    ]
    levels = [SEVERITIES.index(e.severity) for e in new if not e.section_id]
    alerts = [entry for entry in new if entry.section_id]

    if unread_errors:
        severity, accent = SEVERITY_ERROR, ()

    elif attention:
        severity, accent = ALERT_SEVERITY, ATTENTION_ACCENT

    elif levels:
        severity, accent = SEVERITIES[max(levels)], ()

    elif alerts:
        severity, accent = ALERT_SEVERITY, alerts[-1].accent

    else:
        severity, accent = "", ()

    return len(attention) + len(new), severity, accent, len(attention), len(new)


class NotificationsPaneModel(HasTraits):
    """What the drawer, the toasts and the bell show."""

    #: The notifications.
    center = Instance(NotificationCenter, ())

    #: The toasts on screen; their settings are the centre's.
    toasts = Instance(ToastStackModel)

    #: Every section of the drawer's column, in any order: its own Needs
    #: attention and Activity, and the contributed ones.
    sections = List(Instance(NotificationSection))

    #: The sections in the order shown, top first.
    ordered_sections = Property(
        List(Instance(NotificationSection)), observe="sections.items.order"
    )

    #: Whether the drawer is open.
    is_open = Bool(False)

    #: Whether the app opened the drawer (at start-up), not the user: it
    #: then leaves the keyboard focus where it is, closes on Esc anywhere in
    #: its window, and builds its sections one per paced GUI turn. Off again
    #: once it closes.
    opened_by_app = Bool(False)

    #: The drawer's width (px), for the session.
    drawer_width = Int(DRAWER_WIDTH)

    #: Which Activity entries show.
    history_filter = Enum(*FILTERS)

    #: Whether a help link can open anything; while not, help links are
    #: disabled and say so.
    help_available = Bool(False)

    mark_all_read_button = Button()
    clear_all_button = Button()
    close_button = Button()
    settings_button = Button()

    #: Fired with the entry the user dismissed.
    dismiss = Event(Instance(Notification))

    #: Fired with the entry whose first, or second, button the user pressed.
    run_action = Event(Instance(Notification))
    run_secondary_action = Event(Instance(Notification))

    #: Fired with an entry the open drawer scrolls to and highlights.
    reveal = Event(Instance(Notification))

    #: Fired with an arrival the bell rings (and chimes) for: a new toast,
    #: a refreshed one, or one landing in the open drawer.
    rang = Event(Instance(Notification))

    #: Fired with ``(entry, reason)`` for an arrival the bell does not ring
    #: for: start-up history, one already read, one held while quiet.
    silenced = Event(Tuple(Instance(Notification), Str))

    #: Stand-ins for the sections' alerts (SectionAlert), oldest first:
    #: unread until seen in the open drawer, new until it closes.
    section_alerts = List(Instance(Notification))

    #: The bell's count (``bell_summary``): the Needs attention entries not
    #: yet resolved, read or not, and the other unread entries and alerts
    #: not on screen as toasts; and those two parts, for its tooltip.
    #: Plain traits, recounted here (#1134).
    bell_count = Int(0)
    bell_attention = Int(0)
    bell_new = Int(0)

    #: The most urgent severity counted; ALERT_SEVERITY when only alerts
    #: are, then in ``bell_accent``; "" when nothing is.
    bell_severity = Str()
    bell_accent = Tuple()

    def _toasts_default(self):
        return ToastStackModel(settings=self.center.settings)

    def _get_ordered_sections(self):
        return sorted(self.sections, key=lambda section: section.order)

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def expand_section(self, section_id):
        """Expand the section with ``section_id``, if there is one."""
        section = self.section(section_id)

        if section is not None:
            section.expanded = True

    def section(self, section_id):
        """The section with ``section_id``, or None."""
        return next((s for s in self.sections if s.id == section_id), None)

    def reveal_entry(self, entry):
        """Open the drawer on ``entry``."""
        self.is_open = True
        self.reveal = entry

    @observe("is_open")
    def _forget_who_opened(self, event):

        if not event.new:
            self.opened_by_app = False

    # ------------------------------------------------------------------ #
    # The bell's count                                                    #
    # ------------------------------------------------------------------ #

    @observe("center:[unread_count, unread_severity, bulk_changed]")
    @observe("center:entries.items")
    @observe("center:entries:items:needs_attention")
    @observe("toasts:items.items")
    @observe("section_alerts.items.unread")
    def _recount_bell(self, event):
        shown = set(map(id, self.toasts.entries_shown()))
        entries = [*self.center.entries, *self.section_alerts]
        count, severity, accent, attention, new = bell_summary(entries, shown)

        self.trait_set(
            bell_count=count,
            bell_severity=severity,
            bell_accent=accent,
            bell_attention=attention,
            bell_new=new,
        )

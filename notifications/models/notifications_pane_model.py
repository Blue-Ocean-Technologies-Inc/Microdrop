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
from traits.observation.api import ListChangeEvent, trait

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_UNFOLD_LESS, ICON_UNFOLD_MORE

# Local imports.
from ..consts import (
    ATTENTION_SECTION_ID,
    DRAWER_WIDTH,
    SEVERITIES,
    SEVERITY_ERROR,
    NotificationSection,
)
from .notification import Notification
from .notification_center import NotificationCenter
from .own_sections import ATTENTION_ACCENT, FILTERS
from .toasts import ToastStackModel

#: The bell's "severity" while it counts only section alerts (new posts):
#: below info, drawn in the newest alert's accent.
ALERT_SEVERITY = "alert"

#: The header's fold-all toggle, ``(expand, glyph, tooltip)``: while any
#: shown section is expanded, and while none is.
COLLAPSE_ALL = (False, ICON_UNFOLD_LESS, "Collapse all sections")
EXPAND_ALL = (True, ICON_UNFOLD_MORE, "Expand all sections")


def fold_all_toggle(sections):
    """What the header's fold-all toggle does for ``sections``:
    COLLAPSE_ALL while any shown section is expanded, else EXPAND_ALL. A
    hidden section (Needs attention while empty) does not count."""
    shown = [section for section in sections if getattr(section, "available", True)]

    return COLLAPSE_ALL if any(section.expanded for section in shown) else EXPAND_ALL


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


def outside_press_passes_through(opened_by_app, used_while_open):
    """Whether a press outside the open drawer, which closes it, also
    reaches what was pressed: yes for a drawer the app opened and the user
    has not clicked or scrolled in yet, so their first click in the window
    is not lost; no for a drawer that is the user's, where the press is
    used up and never also actuates what lies beneath."""
    return opened_by_app and not used_while_open


def next_section_to_build(queued, opened_by_app):
    """Which of the ``queued`` sections (oldest first) the drawer builds
    next: Needs attention, then in a drawer the app opened the first shown
    expanded at start (News), even if it arrived after the others; else the
    oldest."""
    urgent = [section for section in queued if section.expanded_at_start]
    attention = [section for section in queued if section.id == ATTENTION_SECTION_ID]

    if attention:
        return attention[0]

    if opened_by_app and urgent:
        return urgent[0]

    return queued[0]


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
    #: its window, builds its sections one per paced GUI turn, the
    #: ``expanded_at_start`` ones first (``next_section_to_build``), expands
    #: those, and late arrivals too, and lets a press outside it through,
    #: until the user uses it. Off again once it closes.
    opened_by_app = Bool(False)

    #: Whether the user has clicked or scrolled inside the open drawer, or
    #: folded every section at once: an app-opened drawer is then theirs
    #: (``outside_press_passes_through``). Off again once it closes.
    used_while_open = Bool(False)

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

    #: Collapse every section, or expand them all: what ``fold_all`` says.
    fold_all_button = Button()

    #: What ``fold_all_button`` does now (``fold_all_toggle``):
    #: ``(expand, glyph, tooltip)``.
    fold_all = Property(
        Tuple,
        observe=[
            "sections.items.expanded",
            trait("sections").list_items().trait("available", optional=True),
        ],
    )

    #: True while ``set_all_sections_expanded`` changes the sections: the
    #: views show each change at once, not folding section by section.
    folding_all = Bool(False)

    #: Fired with the state every section was given (True: expanded), once
    #: all have it.
    folded_all = Event(Bool)

    #: Fired with the entry the user dismissed.
    dismiss = Event(Instance(Notification))

    #: Fired with the entry whose first, or second, button the user pressed.
    run_action = Event(Instance(Notification))
    run_secondary_action = Event(Instance(Notification))

    #: Fired with the path of a detail link the user clicked.
    open_link = Event(Str)

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

    def _get_fold_all(self):
        return fold_all_toggle(self.sections)

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def expand_section(self, section_id):
        """Expand the section with ``section_id``, if there is one."""
        section = self.section(section_id)

        if section is not None:
            section.expanded = True

    def set_all_sections_expanded(self, expanded):
        """Expand (or collapse) every section, and through its
        ``set_all_expanded`` its own sub-sections, as one change: the views
        show it at once (``folding_all``), then ``folded_all`` fires. The
        open drawer is then the user's, so no start-up expansion undoes it."""
        self.folding_all = True

        try:
            for section in self.sections:
                section.expanded = expanded
                section.set_all_expanded(expanded)

        finally:
            self.folding_all = False

        if self.is_open:
            self.used_while_open = True

        self.folded_all = expanded

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
            self.trait_set(opened_by_app=False, used_while_open=False)

    # ------------------------------------------------------------------ #
    # Opened by the app                                                   #
    # ------------------------------------------------------------------ #

    @observe("opened_by_app")
    def _expand_at_start(self, event):
        """The app's opening shows the sections that ask for it expanded."""

        if event.new:
            self._expand_sections_at_start(self.sections)

    @observe("sections.items")
    def _expand_arrivals_at_start(self, event):
        """A section arriving in the drawer the app opened (News, from a
        deferred plugin), before the user uses it, shows as if it had been
        there at the opening; the sections already there keep what the user
        made of them."""

        if not self.opened_by_app or self.used_while_open:
            return

        if isinstance(event, ListChangeEvent):
            arrived = event.added

        else:
            arrived = [s for s in event.new if s not in event.old]

        self._expand_sections_at_start(arrived)

    def _expand_sections_at_start(self, sections):

        for section in sections:
            if section.expanded_at_start:
                section.expanded = True

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

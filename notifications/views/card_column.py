# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A section's notification cards, unscrolled, at their natural height.

For Activity, with filter chips, day headings (Today / Yesterday / Earlier)
and cards built a batch at a time, as the drawer's scroll nears the end.
Cards are never built in one long GUI turn: each turn builds and shows them
for at most BUILD_BUDGET_MS, the first turn included, and the rest follow
in the turns after, so opening the drawer on a full history never stalls.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Any, HasTraits, Instance, observe

# Local imports.
from ..models.notifications_pane_model import NotificationsPaneModel
from ..models.own_sections import (
    FILTER_ALL,
    CardListSection,
    filter_counts,
    matches_filter,
    time_group,
)
from .activity_parts import (
    EMPTY_FILTER_TEXT,
    DayHeading,
    EmptyState,
    FilterChips,
    muted_style_sheet,
)
from .card import NotificationCard
from .view_consts import BUILD_BUDGET_MS, HISTORY_PAGE, TIME_REFRESH_MS

#: Space (px) between cards, and around them.
CARD_SPACING = 8
COLUMN_MARGINS = (2, 2, 6, 6)

#: Every entry has a card outside Activity.
UNLIMITED = 10**9


def make_card(entry, pane_model, parent):
    """A drawer card for ``entry`` whose clicks go to ``pane_model``."""
    card = NotificationCard(entry, parent, help_available=pane_model.help_available)

    card.dismiss_clicked.connect(lambda entry: setattr(pane_model, "dismiss", entry))
    card.action_clicked.connect(lambda entry: setattr(pane_model, "run_action", entry))
    card.secondary_clicked.connect(
        lambda entry: setattr(pane_model, "run_secondary_action", entry)
    )
    card.expand_clicked.connect(_toggle_expanded)
    card.link_clicked.connect(
        lambda entry, path: setattr(pane_model, "open_link", path)
    )

    return card


def _toggle_expanded(entry):
    entry.expanded = not entry.expanded


class _ColumnBinding(HasTraits):
    """Asks its column to re-list when the entries or the filter change."""

    pane_model = Instance(NotificationsPaneModel)

    view = Any()

    @observe("pane_model:center:entries.items.[needs_attention, acted, last_seen]")
    @observe("pane_model:history_filter")
    def _relist(self, event):
        self.view.schedule_relist()

    @observe("pane_model:help_available")
    def _show_help(self, event):
        self.view.show_help_available(event.new)


class CardColumn(QtWidgets.QWidget):
    """The cards of a CardListSection's entries.

    ``activity`` adds the filter chips and day headings, sorts by time and
    builds only the first cards, more on ``load_more()``.
    """

    def __init__(self, section, pane_model, activity=False, parent=None):
        super().__init__(parent)

        self.section = section
        self.pane_model = pane_model
        self.activity = activity

        #: How many of the entries have cards; grows as the scroll nears the
        #: end. Every entry, outside Activity.
        self.limit = HISTORY_PAGE if activity else UNLIMITED

        #: Whether cards are still to build, in the coming GUI turns.
        self.building = False

        #: The cards by entry id, and the day headings by text.
        self._cards = {}
        self._headings = {}
        self._relist_queued = False

        #: The entries shown, in order, filtered and sorted.
        self._shown = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(*COLUMN_MARGINS)
        layout.setSpacing(0)

        self.chips = None

        if activity:
            self.chips = FilterChips(self)
            self.chips.chosen.connect(
                lambda name: setattr(pane_model, "history_filter", name)
            )
            layout.addWidget(self.chips)

        self._items = QtWidgets.QVBoxLayout()
        self._items.setSpacing(CARD_SPACING)
        layout.addLayout(self._items)

        self._more = QtWidgets.QLabel(self)
        self._more.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._more.setContentsMargins(0, 10, 0, 4)
        self._more.hide()
        layout.addWidget(self._more)

        self._empty = EmptyState(self)
        self._empty.hide()
        layout.addWidget(self._empty)

        self._time_refresh = QtCore.QTimer(self)
        self._time_refresh.setInterval(TIME_REFRESH_MS)
        self._time_refresh.timeout.connect(self._refresh_times)
        self._time_refresh.start()

        self._binding = _ColumnBinding(pane_model=pane_model, view=self)

        # The first cards come in the next turn: building the column itself
        # stays cheap.
        self.schedule_relist()

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def schedule_relist(self):
        """Re-list once, after the current burst of changes."""

        if not self._relist_queued:
            self._relist_queued = True
            QtCore.QTimer.singleShot(0, self.relist)

    def has_more(self):
        """Whether entries are left without cards."""
        return self.limit < len(self._shown)

    def load_more(self):
        """Build the next batch of cards."""

        if self.has_more():
            self.limit += HISTORY_PAGE
            self.relist()

    def card_for(self, entry):
        """The card of ``entry``, built if need be (the filter dropped and
        the batches extended to reach it); None if not listed here."""

        if self.activity and not matches_filter(entry, self.pane_model.history_filter):
            self.pane_model.history_filter = FILTER_ALL

        self.relist(build_all=True)

        if entry not in self._shown:
            return None

        position = self._shown.index(entry)

        if position >= self.limit:
            self.limit = (position // HISTORY_PAGE + 1) * HISTORY_PAGE
            self.relist(build_all=True)

        return self._cards.get(id(entry))

    def show_help_available(self, available):
        """Enable or disable every card's help link."""

        for card in self._cards.values():
            card.set_help_available(available)

    def dispose(self):
        """Stop following the model and the entries."""
        self._binding.pane_model = None
        self._time_refresh.stop()

        for card in self._cards.values():
            card.dispose()

    # ------------------------------------------------------------------ #
    # Listing                                                             #
    # ------------------------------------------------------------------ #

    def relist(self, build_all=False):
        """Show cards for the first ``limit`` entries, under day headings,
        reusing what is built. New cards are built and shown for at most
        BUILD_BUDGET_MS per GUI turn (unless ``build_all``)."""
        self._relist_queued = False

        if self._binding.pane_model is None:
            return

        entries = list(self.section.entries())
        current = self.pane_model.history_filter

        if self.activity:
            self.chips.show_state(current, filter_counts(entries))
            entries = [entry for entry in entries if matches_filter(entry, current)]
            entries.sort(key=lambda entry: entry.last_seen, reverse=True)

        self._shown = entries
        deadline = time.perf_counter() + BUILD_BUDGET_MS / 1000
        wanted = self._wanted_widgets(entries[: self.limit], build_all, deadline)

        self._drop_unwanted(wanted)

        listed = self._list(wanted, build_all, deadline)
        cards = sum(isinstance(widget, NotificationCard) for widget in listed)
        self.building = cards < min(self.limit, len(entries))

        if self.building:
            self.schedule_relist()

        hidden = len(entries) - cards
        self._more.setVisible(bool(hidden) and not self.building)
        self._more.setText(f"{hidden} earlier — scroll for more")
        self._more.setStyleSheet(muted_style_sheet())

        self._empty.setVisible(self.activity and not entries)
        self._empty.set_hint(EMPTY_FILTER_TEXT.get(current, ""))

    def _wanted_widgets(self, entries, build_all, deadline):
        """The cards for the first of ``entries``, those still missing built
        until ``deadline`` (time.perf_counter()), with day headings between
        them."""
        widgets = []
        heading = None
        now = time.time()

        for entry in entries:
            card = self._cards.get(id(entry))

            if card is None and not build_all and time.perf_counter() > deadline:
                break

            if self.activity and time_group(entry.last_seen, now) != heading:
                heading = time_group(entry.last_seen, now)
                widgets.append(self._heading(heading))

            if card is None:
                card = make_card(entry, self.pane_model, self)
                card.hide()
                self._cards[id(entry)] = card

            widgets.append(card)

        return widgets

    def _list(self, wanted, build_all, deadline):
        """Put ``wanted`` in the layout in order, showing the new ones until
        ``deadline``: showing a card (styling its parts) costs more than
        building it. Returns the widgets listed."""
        shown_new = 0

        for position, widget in enumerate(wanted):
            new = widget.isHidden() and isinstance(widget, NotificationCard)
            late = time.perf_counter() > deadline

            # At least one new card per turn, so the building always ends.
            if new and shown_new and not build_all and late:
                return wanted[:position]

            if self._items.indexOf(widget) != position:
                self._items.removeWidget(widget)
                self._items.insertWidget(position, widget)

            if widget.isHidden():
                widget.show()
                shown_new += new

        return wanted

    def _heading(self, text):
        heading = self._headings.get(text)

        if heading is None:
            heading = self._headings[text] = DayHeading(text, self)

        return heading

    def _drop_unwanted(self, wanted):
        """Delete the cards no longer listed; hide unused headings."""
        keep = set(map(id, wanted))

        for key, card in list(self._cards.items()):
            if id(card) not in keep:
                del self._cards[key]
                self._items.removeWidget(card)
                card.dispose()
                card.hide()
                card.deleteLater()

        for heading in self._headings.values():
            if id(heading) not in keep:
                self._items.removeWidget(heading)
                heading.hide()

    def _refresh_times(self):

        if not self.isVisible():
            return

        for card in self._cards.values():
            card.refresh_time()


def is_card_list(section):
    """Whether ``section`` is one of the drawer's own card lists."""
    return isinstance(section, CardListSection)

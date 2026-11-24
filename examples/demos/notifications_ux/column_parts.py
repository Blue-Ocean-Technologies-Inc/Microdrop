# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What the drawer's one-column layout puts in its sections, each at its
natural height, none scrolling by itself:

* ``CardColumn``: notification cards. For Activity, with filter chips, day
  headings (Today / Yesterday / Earlier) and cards built only a batch at a
  time, as the column's scroll nears the end.
* The News feed and its sub-sections are in ``feed_column``.
* ``fit_item_views``: grows a contributed section's lists and tables to all
  their rows, so they need no scroll bar of their own.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, HasTraits, Instance, observe

# Microdrop package imports.
from notifications.consts import SEVERITY_COLORS, SEVERITY_ERROR, TIME_REFRESH_MS

# Microdrop style imports.
from microdrop_style.colors import GREY, WHITE

# Local imports.
from .card_list_view import EmptyState, make_card
from .card_view import NotificationCard
from .typography import CHIP, role_font
from .ux_consts import (
    ATTENTION_ACCENT,
    BUILD_BUDGET_MS,
    FILTER_ACTION,
    FILTER_ALL,
    FILTER_ERRORS,
    HISTORY_PAGE,
)
from .ux_models import UxPaneModel, matches_filter, time_group
from .view_styles import (
    contrast,
    css,
    is_dark,
    muted_text,
    readable_accent,
    style_chip,
    with_alpha,
)

#: The filter chips: (filter, label), left to right.
FILTER_CHIPS = [
    (FILTER_ALL, "All"),
    (FILTER_ERRORS, "Errors"),
    (FILTER_ACTION, "Needs action"),
]

#: Each filter chip's colour, ``(light theme, dark theme)``: All a quiet
#: slate, Errors the error red, Needs action Needs attention's orange.
FILTER_CHIP_ACCENTS = {
    FILTER_ALL: (GREY["dark"], GREY["lighter"]),
    FILTER_ERRORS: (SEVERITY_COLORS[SEVERITY_ERROR], SEVERITY_COLORS[SEVERITY_ERROR]),
    FILTER_ACTION: (ATTENTION_ACCENT, ATTENTION_ACCENT),
}

#: What an empty, filtered Activity says.
EMPTY_FILTER_TEXT = {
    FILTER_ERRORS: "No errors.",
    FILTER_ACTION: "Nothing waiting for you.",
}

#: Space (px) between cards, and around them.
CARD_SPACING = 8
COLUMN_MARGINS = (2, 2, 6, 6)


# ---------------------------------------------------------------------------
# Filter chips and day headings
# ---------------------------------------------------------------------------


class FilterChips(QtWidgets.QWidget):
    """One pill per filter, with its count; one is chosen at a time."""

    chosen = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 8)
        layout.setSpacing(6)

        self._group = QtWidgets.QButtonGroup(self)
        self._chips = {}
        self._counts = {}

        for name, label in FILTER_CHIPS:
            chip = QtWidgets.QPushButton(label, self)
            chip.setFont(role_font(CHIP))
            chip.setCheckable(True)
            chip.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda checked, name=name: self.chosen.emit(name))
            self._group.addButton(chip)
            self._chips[name] = (chip, label)
            layout.addWidget(chip)

        layout.addStretch(1)
        self.restyle()

    def show_state(self, current, counts):
        """Check ``current``; label each chip with its count."""

        for name, (chip, label) in self._chips.items():
            chip.setChecked(name == current)
            chip.setText(f"{label}  {counts.get(name, 0)}")

        self._counts = dict(counts)
        self.restyle()

    def restyle(self):
        """Each chip in its own colour: outlined and tinted, filled when
        chosen, muted while it counts nothing."""
        palette = QtWidgets.QApplication.palette()
        dark = is_dark(palette)
        muted = muted_text(palette)

        for name, (chip, _label) in self._chips.items():
            accent = QtGui.QColor(FILTER_CHIP_ACCENTS[name][1 if dark else 0])
            readable = readable_accent(accent, palette)
            on_fill = WHITE if contrast(QtGui.QColor(WHITE), accent) >= 3 else "#000000"
            empty = not self._counts.get(name, 0)
            text = muted if empty else readable
            edge = with_alpha(muted if empty else accent, 0.3 if empty else 0.55)

            style_chip(
                chip,
                f"color: {css(text)}; background: {css(with_alpha(accent, 0.07))};"
                f" border: 1px solid {css(edge)};",
                f"QPushButton:hover {{ background: {css(with_alpha(accent, 0.15))}; }}"
                " QPushButton:checked {"
                f" color: {on_fill}; background: {css(accent)};"
                f" border-color: {css(accent)}; }}",
            )

    def event(self, event):

        if event.type() == QtCore.QEvent.Type.ApplicationPaletteChange:
            self.restyle()

        return super().event(event)


class DayHeading(QtWidgets.QLabel):
    """A small, muted heading over a day's cards."""

    def __init__(self, text, parent=None):
        super().__init__(text.upper(), parent)

        self.setFont(role_font(CHIP))
        self.setContentsMargins(6, 8, 0, 0)
        self.restyle()

    def restyle(self):
        # Its own style sheet changes its palette: read the application's.
        palette = QtWidgets.QApplication.palette()
        self.setStyleSheet(f"color: {muted_text(palette).name()};")

    def event(self, event):

        if event.type() == QtCore.QEvent.Type.ApplicationPaletteChange:
            self.restyle()

        return super().event(event)


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


class _ColumnBinding(HasTraits):
    """Asks its column to re-list when the entries or the filter change."""

    pane_model = Instance(UxPaneModel)

    view = Any()

    @observe("pane_model:center:entries.items.[needs_attention, acted, last_seen]")
    @observe("pane_model:history_filter")
    def _relist(self, event):
        self.view.schedule_relist()


class CardColumn(QtWidgets.QWidget):
    """The cards of ``pane_model.center.<entries_name>``, unscrolled.

    ``activity`` adds the filter chips and day headings, sorts by time and
    builds only the first cards, more on ``load_more()``.
    """

    #: The cards changed: the column's height may have too.
    content_changed = QtCore.Signal()

    def __init__(self, pane_model, entries_name, activity=False, parent=None):
        super().__init__(parent)

        self.pane_model = pane_model
        self.entries_name = entries_name
        self.activity = activity

        #: How many of the entries have cards; grows as the scroll nears the
        #: end. Every entry, outside Activity.
        self.limit = HISTORY_PAGE if activity else 10**9

        #: The cards by entry id, and the day headings by text.
        self._cards = {}
        self._headings = {}
        self._relist_queued = False

        #: Whether cards are still to build, in the coming GUI turns.
        self.building = False

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
        layout.addWidget(self._more)

        self._empty = EmptyState(self)
        layout.addWidget(self._empty)

        self._time_refresh = QtCore.QTimer(self)
        self._time_refresh.setInterval(TIME_REFRESH_MS)
        self._time_refresh.timeout.connect(self._refresh_times)
        self._time_refresh.start()

        self._binding = _ColumnBinding(pane_model=pane_model, view=self)
        self.relist()

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

    def dispose(self):
        """Stop following the model and the entries."""
        self._binding.pane_model = None

        for card in self._cards.values():
            card.dispose()

    # ------------------------------------------------------------------ #
    # Listing                                                             #
    # ------------------------------------------------------------------ #

    def relist(self, build_all=False):
        """Show cards for the first ``limit`` entries, under day headings,
        reusing what is built. New cards are built for at most
        BUILD_BUDGET_MS per GUI turn (unless ``build_all``); the rest
        follow in the next turns."""
        self._relist_queued = False
        entries = list(getattr(self.pane_model.center, self.entries_name))
        current = self.pane_model.history_filter

        if self.activity:
            self.chips.show_state(current, self._counts(entries))
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
        self._more.setStyleSheet(f"color: {muted_text(self.palette()).name()};")

        self._empty.setVisible(self.activity and not entries)
        self._empty.set_hint(EMPTY_FILTER_TEXT.get(current, ""))
        self.content_changed.emit()

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
                card = self._cards[id(entry)] = make_card(entry, self.pane_model, self)
                card.hide()

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

    @staticmethod
    def _counts(entries):
        return {
            FILTER_ALL: len(entries),
            FILTER_ERRORS: sum(entry.severity == SEVERITY_ERROR for entry in entries),
            FILTER_ACTION: sum(
                matches_filter(entry, FILTER_ACTION) for entry in entries
            ),
        }

    def _refresh_times(self):

        for card in self._cards.values():
            card.refresh_time()


# ---------------------------------------------------------------------------
# Contributed sections
# ---------------------------------------------------------------------------


def fit_item_views(widget):
    """Grow every list and table in ``widget`` to show all its rows, and
    again when they change, so none needs a scroll bar of its own."""

    for view in widget.findChildren(QtWidgets.QAbstractItemView):
        _fit(view)

        model = view.model()

        if model is not None:
            for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
                signal.connect(lambda *args, view=view: _fit_later(view))


def _fit_later(view):
    QtCore.QTimer.singleShot(0, lambda: _fit(view))


def _fit(view):
    """Fix ``view``'s height to its rows, its header and its frame."""

    try:
        if isinstance(view, QtWidgets.QTableView):
            rows = view.verticalHeader().length()
            header = view.horizontalHeader().height()

        else:
            rows = max(view.sizeHintForRow(0), 0) * view.model().rowCount()
            header = 0

    # Deleted with its section.
    except RuntimeError:
        return

    view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setFixedHeight(rows + header + 2 * view.frameWidth() + 2)

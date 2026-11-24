# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A drawer section's cards: a scrolled column of NotificationCards over one
of the centre's entry lists, with an empty state.

Its background is left unpainted, so the drawer's translucency shows between
the cards. Clicks go back to the pane model as its ``dismiss``,
``run_action`` and ``run_secondary_action`` events. Runs standalone against
just a model::

    CardListView(UxPaneModel(), "history_entries").show()
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, HasTraits, Instance, Str, observe

# Microdrop package imports.
from notifications.consts import TIME_REFRESH_MS

# Local imports.
from .card_view import NotificationCard
from .ux_models import UxPaneModel
from .view_styles import icon_font, muted_text, text_font

#: Space (px) between cards, and around the column.
CARD_SPACING = 8
LIST_MARGINS = (2, 4, 6, 8)

#: The empty state's glyph, headline and hint.
EMPTY_GLYPH = "notifications_paused"
EMPTY_TITLE = "You're all caught up"
EMPTY_HINT = "New notifications pop up by the bell and are kept here."


def make_card(entry, pane_model, parent):
    """A drawer card for ``entry`` whose clicks go to ``pane_model``."""
    card = NotificationCard(entry, parent)

    card.dismiss_clicked.connect(lambda entry: setattr(pane_model, "dismiss", entry))
    card.action_clicked.connect(lambda entry: setattr(pane_model, "run_action", entry))
    card.secondary_clicked.connect(
        lambda entry: setattr(pane_model, "run_secondary_action", entry)
    )
    card.expand_clicked.connect(_toggle_expanded)

    return card


def _toggle_expanded(entry):
    entry.expanded = not entry.expanded


class EmptyState(QtWidgets.QWidget):
    """A large muted glyph over a headline and a hint, centred."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 28)
        layout.setSpacing(6)
        layout.addStretch(1)

        self._glyph = QtWidgets.QLabel(EMPTY_GLYPH, self)
        self._glyph.setFont(icon_font(44))
        self._title = QtWidgets.QLabel(EMPTY_TITLE, self)
        self._title.setFont(text_font(self.font(), 1.5, QtGui.QFont.Weight.DemiBold))
        self._hint = QtWidgets.QLabel(EMPTY_HINT, self)
        self._hint.setWordWrap(True)

        for label in (self._glyph, self._title, self._hint):
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

        layout.addStretch(2)
        self._restyle()

    def set_hint(self, title):
        """Say ``title`` alone (a filter's "No errors."), or the default
        headline and hint when empty."""
        self._title.setText(title or EMPTY_TITLE)
        self._hint.setVisible(not title)

    def _restyle(self):
        muted = muted_text(self.palette()).name()

        self._glyph.setStyleSheet(f"color: {muted};")
        self._hint.setStyleSheet(f"color: {muted};")

    def changeEvent(self, event):
        super().changeEvent(event)

        if event.type() == QtCore.QEvent.Type.PaletteChange:
            self._restyle()


class _ListBinding(HasTraits):
    """Asks its view to re-list the cards when its entries change."""

    pane_model = Instance(UxPaneModel)

    #: The centre's list followed.
    entries_name = Str()

    view = Any()

    # The plain traits under the centre's entry-list Properties.
    @observe("pane_model:center:entries.items.needs_attention")
    def _entries_changed(self, event):
        self.view.schedule_relist()


class CardListView(QtWidgets.QScrollArea):
    """The cards of ``pane_model.center.<entries_name>``, newest first."""

    #: The cards changed: the height they need may have too.
    content_changed = QtCore.Signal()

    def __init__(self, pane_model, entries_name, parent=None):
        super().__init__(parent)

        self.pane_model = pane_model
        self.entries_name = entries_name

        #: Each listed entry's card.
        self._cards = {}
        self._relist_scheduled = False

        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; }")
        self.viewport().setAutoFillBackground(False)

        self._column = QtWidgets.QWidget()
        self._column.setAutoFillBackground(False)
        self._layout = QtWidgets.QVBoxLayout(self._column)
        self._layout.setContentsMargins(*LIST_MARGINS)
        self._layout.setSpacing(CARD_SPACING)
        self._layout.addStretch(1)
        self.setWidget(self._column)

        self._empty = EmptyState(self._column)
        self._layout.insertWidget(0, self._empty)

        self._time_refresh = QtCore.QTimer(self)
        self._time_refresh.setInterval(TIME_REFRESH_MS)
        self._time_refresh.timeout.connect(self._refresh_times)

        self._binding = _ListBinding(
            pane_model=pane_model, entries_name=entries_name, view=self
        )
        self.relist()

    # ------------------------------------------------------------------ #
    # Listing                                                             #
    # ------------------------------------------------------------------ #

    def schedule_relist(self):
        """Re-list once, after the current burst of changes."""

        if not self._relist_scheduled:
            self._relist_scheduled = True
            QtCore.QTimer.singleShot(0, self.relist)

    def relist(self):
        """Make the column show the entries, in order, reusing cards."""
        self._relist_scheduled = False
        entries = getattr(self.pane_model.center, self.entries_name)
        listed = set(map(id, entries))

        for key in [key for key in self._cards if key not in listed]:
            card = self._cards.pop(key)
            card.dispose()
            card.hide()
            card.deleteLater()

        for position, entry in enumerate(entries):
            card = self._cards.get(id(entry))

            if card is None:
                card = self._cards[id(entry)] = self._make_card(entry)

            # Index 0 is the empty state.
            if self._layout.indexOf(card) != position + 1:
                self._layout.removeWidget(card)
                self._layout.insertWidget(position + 1, card)

        self._empty.setVisible(not entries)
        self.content_changed.emit()

    def content_height(self):
        """Pixels the cards need at the current width, unscrolled."""
        width = max(self.viewport().width(), 200)
        height = self._column.heightForWidth(width)

        return height if height > 0 else self._column.sizeHint().height()

    def _make_card(self, entry):
        return make_card(entry, self.pane_model, self._column)

    # ------------------------------------------------------------------ #
    # Times                                                               #
    # ------------------------------------------------------------------ #

    def _refresh_times(self):
        for card in self._cards.values():
            card.refresh_time()

    def showEvent(self, event):
        super().showEvent(event)

        self._refresh_times()
        self._time_refresh.start()

    def hideEvent(self, event):
        super().hideEvent(event)

        self._time_refresh.stop()

    def dispose(self):
        """Stop following the model and the entries."""
        self._binding.pane_model = None

        for card in self._cards.values():
            card.dispose()

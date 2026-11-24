# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Making a drawer card wired to the pane model, and the empty state shown
where there are no cards. Clicks go back to the pane model as its
``dismiss``, ``run_action`` and ``run_secondary_action`` events."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Local imports.
from .card_view import NotificationCard
from .view_styles import icon_font, muted_text, text_font

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

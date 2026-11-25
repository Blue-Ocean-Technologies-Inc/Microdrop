# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Activity's pieces around its cards: the filter chips, the day headings,
and the empty state."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop style imports.
from microdrop_style.color_contrast import label_on
from microdrop_style.palette_helpers import css, icon_font, style_chip, with_alpha

# Local imports.
from ..models.own_sections import FILTER_ACTION, FILTER_ALL, FILTER_ERRORS
from . import colour_roles
from .theme import accent_of, chip_tint, muted_text, readable_accent, theme_palette
from .typography import CARD_TITLE, CHIP, role_font

#: The filter chips: (filter, label), left to right.
FILTER_CHIPS = [
    (FILTER_ALL, "All"),
    (FILTER_ERRORS, "Errors"),
    (FILTER_ACTION, "Needs action"),
]

#: Each filter chip's colour, ``(light theme, dark theme)``: All a quiet
#: grey, Errors the error red, Needs action Needs attention's orange.
FILTER_CHIP_ACCENTS = {
    FILTER_ALL: colour_roles.NEUTRAL_FILL,
    FILTER_ERRORS: colour_roles.ERROR_FILL,
    FILTER_ACTION: colour_roles.ATTENTION_FILL,
}

#: What an empty, filtered Activity says.
EMPTY_FILTER_TEXT = {
    FILTER_ERRORS: "No errors.",
    FILTER_ACTION: "Nothing waiting for you.",
}

#: The empty state's glyph, headline and hint.
EMPTY_GLYPH = "notifications_paused"
EMPTY_TITLE = "You're all caught up"
EMPTY_HINT = "New notifications pop up by the bell and are kept here."

#: A theme switch. Not PaletteChange: setting a widget's own style sheet
#: sends it one, and restyling on it would never end.
_THEME_EVENTS = (QtCore.QEvent.Type.ApplicationPaletteChange,)


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

        # Restyled only when a chip turns empty or no longer is.
        changed = [
            name
            for name in self._chips
            if bool(counts.get(name)) != bool(self._counts.get(name))
        ]
        self._counts = dict(counts)

        if changed:
            self.restyle()

    def restyle(self):
        """Each chip in its own colour: outlined and tinted, filled when
        chosen, muted while it counts nothing."""
        palette = theme_palette()
        muted = muted_text(palette)

        for name, (chip, _label) in self._chips.items():
            accent = accent_of(FILTER_CHIP_ACCENTS[name], palette)
            empty = not self._counts.get(name, 0)
            text = muted if empty else readable_accent(accent, palette)
            edge = with_alpha(muted if empty else accent, 0.3 if empty else 0.55)
            tint = with_alpha(accent, chip_tint(palette) / 2)

            style_chip(
                chip,
                f"color: {css(text)}; background: {css(tint)};"
                f" border: 1px solid {css(edge)};",
                f"QPushButton:hover {{ background: {css(with_alpha(accent, 0.15))}; }}"
                " QPushButton:checked {"
                f" color: {label_on(accent.name())}; background: {css(accent)};"
                f" border-color: {css(accent)}; }}",
            )

    def event(self, event):

        if event.type() in _THEME_EVENTS:
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
        self.setStyleSheet(f"color: {muted_text(theme_palette()).name()};")

    def event(self, event):

        if event.type() in _THEME_EVENTS:
            self.restyle()

        return super().event(event)


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
        self._title.setFont(role_font(CARD_TITLE))
        self._hint = QtWidgets.QLabel(EMPTY_HINT, self)
        self._hint.setWordWrap(True)

        for label in (self._glyph, self._title, self._hint):
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

        layout.addStretch(2)
        self.restyle()

    def set_hint(self, title):
        """Say ``title`` alone (a filter's "No errors."), or the default
        headline and hint when empty."""
        self._title.setText(title or EMPTY_TITLE)
        self._hint.setVisible(not title)

    def restyle(self):
        muted = muted_text(theme_palette()).name()

        self._glyph.setStyleSheet(f"color: {muted};")
        self._hint.setStyleSheet(f"color: {muted};")

    def event(self, event):

        if event.type() in _THEME_EVENTS:
            self.restyle()

        return super().event(event)


def muted_style_sheet():
    """A label's style sheet in the muted text colour."""
    return f"color: {muted_text(theme_palette()).name()};"

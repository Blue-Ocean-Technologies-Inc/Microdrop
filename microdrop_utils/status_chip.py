# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fully rounded status-bar chips on a soft status-colour wash, the compact
menu a chip opens, and the severity colours they share. A file chip's
colour carries its state: muted with no file, green saved, amber unsaved,
red in error."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop style imports.
from microdrop_style import colour_roles
from microdrop_style.icons.icons import ICON_WARNING
from microdrop_style.palette_helpers import css, icon_font, with_alpha
from microdrop_style.panel_theme import (
    chip_text,
    muted_text,
    role_color,
    theme_palette,
)
from microdrop_style.typography import CHIP, role_font

#: Height of every status-bar chip, px; the chips are fully rounded.
CHIP_HEIGHT = 22

#: Widest a chip's name grows before it elides, and the narrowest a chip
#: shrinks to, px.
NAME_MAX_WIDTH = 160
CHIP_MIN_WIDTH = 56

#: Wash alpha of a calm chip (neutral, saved, ready) and of an alerting one.
CALM_ALPHA = 0.11
ALERT_ALPHA = 0.14

#: How much stronger the wash grows on hover.
HOVER_BOOST = 0.09

#: File-chip state -> its severity (None: muted) and wash alpha.
FILE_CHIP_STATES = {
    "neutral": (None, CALM_ALPHA),
    "saved": ("success", CALM_ALPHA),
    "unsaved": ("warning", ALERT_ALPHA),
    "error": ("error", ALERT_ALPHA),
}

#: The amber chip's tooltip note.
UNSAVED_NOTE = "Unsaved changes"

#: Gap between a chip and the menu it opens above it, px.
MENU_GAP = 4

#: Keys that open a focused chip's menu, as a click does.
ACTIVATE_KEYS = (
    QtCore.Qt.Key.Key_Return,
    QtCore.Qt.Key.Key_Enter,
    QtCore.Qt.Key.Key_Space,
)


def severity_color(severity, palette):
    """The theme's colour for ``severity`` ("info", "success", "warning" or
    "error"); muted text for None."""

    if severity is None:
        return muted_text(palette)

    return role_color(palette, colour_roles.SEVERITY[severity])


def follow_theme(restyle):
    """Call ``restyle`` after every colour-scheme change, queued so the new
    palette has landed. Pass a widget's bound method: the connection then
    goes with the widget."""
    QtWidgets.QApplication.styleHints().colorSchemeChanged.connect(
        restyle, QtCore.Qt.ConnectionType.QueuedConnection
    )


def chip_sheet(selector, accent, alpha):
    """A fully rounded chip ``selector`` washed with ``accent`` at
    ``alpha``, stronger on hover and outlined while it has keyboard
    focus."""
    return (
        f"{selector} {{ background: {css(with_alpha(accent, alpha))};"
        f" border: 1px solid transparent; border-radius: {CHIP_HEIGHT // 2}px; }}"
        f" {selector}:hover {{"
        f" background: {css(with_alpha(accent, alpha + HOVER_BOOST))}; }}"
        f" {selector}:focus {{ border-color: {css(accent)}; }}"
    )


def chip_menu(parent):
    """An empty compact, rounded menu for a chip to fill."""
    palette = theme_palette()
    text = palette.color(palette.ColorRole.Text)
    accent = severity_color("success", palette)

    menu = QtWidgets.QMenu(parent)
    menu.setStyleSheet(
        "QMenu { padding: 4px; border-radius: 6px;"
        f" border: 1px solid {css(with_alpha(text, 0.15))}; }}"
        " QMenu::item { padding: 4px 18px 4px 12px; border-radius: 4px; }"
        f" QMenu::item:selected {{ background: {css(with_alpha(accent, 0.18))};"
        f" color: {css(text)}; }}"
        f" QMenu::item:disabled {{ color: {css(muted_text(palette))}; }}"
        " QMenu::separator { height: 1px; margin: 4px 8px;"
        f" background: {css(with_alpha(text, 0.12))}; }}"
    )

    return menu


def open_menu_above(menu, anchor):
    """Open ``menu`` upward over ``anchor``."""
    height = menu.sizeHint().height()
    menu.exec(anchor.mapToGlobal(QtCore.QPoint(0, -height - MENU_GAP)))


class FileChip(QtWidgets.QFrame):
    """A chip for a file: glyph, elided name and, in error, a warning glyph,
    washed muted (no file), green (saved), amber (unsaved) or red (error).
    The name's text style never changes: the wash and the tooltip carry the
    state. Clicked, or Enter/Space while focused, it emits ``clicked``."""

    #: Pressed.
    clicked = QtCore.Signal()

    def __init__(self, glyph, object_name, parent=None):
        super().__init__(parent)

        self.setObjectName(object_name)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(CHIP_HEIGHT)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 10, 0)
        layout.setSpacing(5)

        self._icon = QtWidgets.QLabel(glyph)
        self._icon.setFont(icon_font(15))

        self._name = QtWidgets.QLabel()
        self._name.setFont(role_font(CHIP))
        self._name.setMinimumWidth(16)
        self._name.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        self._warning = QtWidgets.QLabel(ICON_WARNING)
        self._warning.setFont(icon_font(14))
        self._warning.hide()

        layout.addWidget(self._icon)
        layout.addWidget(self._name, 1)
        layout.addWidget(self._warning)

        self._full_name = ""
        self._state = "neutral"
        self._restyle()

        follow_theme(self._restyle)

    def show_file(self, name, path, unsaved, error=""):
        """Show ``name`` (elided) in its state's colour, ``path`` and the
        notes in the tooltip. ``error``, the note why the file is in error,
        outranks unsaved changes."""
        notes = [error] if error else []

        if unsaved:
            notes.append(UNSAVED_NOTE)

        state = "error" if error else "unsaved" if unsaved else "saved"

        self._show(name, "\n".join([path, *notes]), state)

    def show_neutral(self, name, note):
        """Show ``name`` muted, with ``note`` as the tooltip: no file."""
        self._show(name, note, "neutral")

    def _show(self, name, tooltip, state):
        self._full_name = name
        self._state = state

        self._warning.setVisible(state == "error")
        self.setToolTip(tooltip)
        self._restyle()
        self._elide()
        self.updateGeometry()

    def sizeHint(self):
        layout = self.layout()
        margins = layout.contentsMargins()
        name_width = min(
            self._name.fontMetrics().horizontalAdvance(self._full_name),
            NAME_MAX_WIDTH,
        )
        width = (
            margins.left()
            + self._icon.sizeHint().width()
            + layout.spacing()
            + name_width
            + 2
            + margins.right()
        )

        if self._warning.isVisibleTo(self):
            width += layout.spacing() + self._warning.sizeHint().width()

        return QtCore.QSize(width, CHIP_HEIGHT)

    def minimumSizeHint(self):
        return QtCore.QSize(min(self.sizeHint().width(), CHIP_MIN_WIDTH), CHIP_HEIGHT)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def keyPressEvent(self, event):
        if event.key() in ACTIVATE_KEYS:
            self.clicked.emit()
            event.accept()

            return

        super().keyPressEvent(event)

    def _elide(self):
        metrics = self._name.fontMetrics()
        self._name.setText(
            metrics.elidedText(
                self._full_name,
                QtCore.Qt.TextElideMode.ElideRight,
                max(self._name.width(), 1),
            )
        )

    def _restyle(self, *_):
        palette = theme_palette()
        severity, alpha = FILE_CHIP_STATES[self._state]
        accent = severity_color(severity, palette)
        text = f"color: {css(chip_text(accent, palette))};"

        for label in (self._icon, self._name, self._warning):
            label.setStyleSheet(text)

        self.setStyleSheet(chip_sheet(f"#{self.objectName()}", accent, alpha))

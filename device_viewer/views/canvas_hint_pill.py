# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The hint pill floating at the top centre of the device canvas (#1211): a
plain widget over the view's viewport, not a scene item, so it never scales
with the zoom, and transparent to the mouse, so it never blocks the canvas."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.palette_helpers import css, style_chip
from microdrop_style.panel_theme import card_border, card_fill, theme_palette
from microdrop_style.typography import BODY_TEXT, role_font

# Local imports.
from ..consts import CANVAS_HINT_TOP_MARGIN_PX
from ..models.canvas_hints import CanvasHints

_ROLE = QtGui.QPalette.ColorRole


class _PillBinding(HasTraits):
    """Shows the hints' text on its pill whenever it changes."""

    #: The hints shown.
    hints = Instance(CanvasHints)

    #: The pill showing them.
    pill = Any()

    @observe("hints:text", dispatch="ui")
    def _show_text(self, event):
        self.pill.show_text(event.new)


class CanvasHintPill(QtWidgets.QLabel):
    """Shows ``hints`` over ``viewport``; hidden while there are none."""

    def __init__(self, viewport, hints):
        super().__init__(viewport)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFont(role_font(BODY_TEXT))
        self.apply_theme()

        viewport.installEventFilter(self)
        QtWidgets.QApplication.styleHints().colorSchemeChanged.connect(self.apply_theme)

        self._binding = _PillBinding(hints=hints, pill=self)
        self.show_text(hints.text)

    def apply_theme(self, *args):
        """Take the colours of a notification card in the current theme."""
        palette = theme_palette()

        style_chip(
            self,
            f"background: {css(card_fill(palette))};"
            f" color: {css(palette.color(_ROLE.Text))};"
            f" border: 1px solid {css(card_border(palette))};",
        )

    def show_text(self, text):
        """Show ``text`` at the top centre; hide on none."""
        self.setText(text)
        self.setVisible(bool(text))

        if text:
            self.place()
            self.raise_()

    def place(self):
        """Centre on the viewport's top edge, clamped to its width."""
        viewport = self.parentWidget()

        self.setMaximumWidth(max(viewport.width() - 2 * CANVAS_HINT_TOP_MARGIN_PX, 0))
        self.adjustSize()
        self.move(
            max((viewport.width() - self.width()) // 2, 0), CANVAS_HINT_TOP_MARGIN_PX
        )

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.Resize and self.isVisible():
            self.place()

        return super().eventFilter(watched, event)

    def detach(self):
        """Stop following the hints and the theme before the canvas goes."""
        self._binding.hints = None
        QtWidgets.QApplication.styleHints().colorSchemeChanged.disconnect(
            self.apply_theme
        )

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's fixed header: title, count chip, and its buttons (Mark all
read, Clear all, Settings, Close), which press the model's buttons."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Bool, HasTraits, Instance, observe

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_CLOSE, ICON_DELETE_SWEEP, ICON_DONE_ALL
from microdrop_style.palette_helpers import css, style_chip, with_alpha

# Local imports.
from ..models.notifications_pane_model import NotificationsPaneModel
from .theme import icon_button_style, theme_palette
from .typography import CHIP, DRAWER_TITLE, role_font

#: The settings button's glyph.
ICON_SETTINGS = "settings"

#: A theme switch. Not PaletteChange: setting a widget's own style sheet
#: sends it one, and restyling on it would never end.
_THEME_EVENTS = (QtCore.QEvent.Type.ApplicationPaletteChange,)


class DrawerHeader(QtWidgets.QWidget):
    """Title, count chip, and the drawer's buttons."""

    def __init__(self, model, parent=None):
        super().__init__(parent)

        self.model = model

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 4, 8)
        layout.setSpacing(2)

        self._title = QtWidgets.QLabel("Notifications", self)
        self._title.setFont(role_font(DRAWER_TITLE))
        layout.addWidget(self._title)
        layout.addSpacing(8)

        self._chip = QtWidgets.QLabel(self)
        self._chip.setFont(role_font(CHIP))
        layout.addWidget(self._chip, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

        self.mark_all_read = self._button(
            ICON_DONE_ALL, "Mark all read", "mark_all_read_button"
        )
        self.clear_all = self._button(
            ICON_DELETE_SWEEP, "Clear all (keeps Needs attention)", "clear_all_button"
        )
        self.settings = self._button(
            ICON_SETTINGS, "Notification settings", "settings_button"
        )
        self.close = self._button(ICON_CLOSE, "Close (Esc)", "close_button")

        for button in self._buttons():
            layout.addWidget(button)

        self._binding = _HeaderBinding(model=model, view=self)
        self.restyle()
        self.show_counts()

    def show_counts(self):
        """Show the count chip and enable the buttons that would do
        anything."""
        center = self.model.center
        total = len(center.entries)
        new = center.new_count
        attention = len(center.attention_entries)

        if new:
            text = f"{new} new"

        else:
            text = str(total) if total else ""

        self._chip.setText(text)
        self._chip.setVisible(bool(text))
        self.mark_all_read.setEnabled(bool(new or center.unread_count))
        self.clear_all.setEnabled(total > attention)

    def restyle(self):
        palette = theme_palette()
        # The unread state: the strong text colour, on a faint tint of it.
        text = palette.color(QtGui.QPalette.ColorRole.Text)

        style_chip(
            self._chip, f"color: {css(text)}; background: {css(with_alpha(text, 0.1))};"
        )

        for button in self._buttons():
            button.setStyleSheet(icon_button_style(palette, 20))

        self.update()

    def dispose(self):
        self._binding.model = None

    def _buttons(self):
        return (self.mark_all_read, self.clear_all, self.settings, self.close)

    def _button(self, glyph, tooltip, model_button):
        button = QtWidgets.QToolButton(self)
        button.setText(glyph)
        button.setToolTip(tooltip)
        button.setFixedSize(32, 32)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: setattr(self.model, model_button, True))

        return button

    def event(self, event):

        if event.type() in _THEME_EVENTS:
            self.restyle()

        return super().event(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        text = theme_palette().color(QtGui.QPalette.ColorRole.Text)

        painter.setPen(with_alpha(text, 0.1))
        painter.drawLine(8, self.height() - 1, self.width() - 4, self.height() - 1)


class _HeaderBinding(HasTraits):
    """Keeps the header's counts current, once per burst of changes."""

    model = Instance(NotificationsPaneModel)

    view = Any()

    #: Whether a refresh is queued.
    _queued = Bool(False)

    @observe("model:center:[unread_count, new_count, bulk_changed, entries.items]")
    @observe("model:center:entries:items:needs_attention")
    def _show_counts(self, event):

        if not self._queued:
            self._queued = True
            QtCore.QTimer.singleShot(0, self._refresh)

    def _refresh(self):
        self._queued = False

        if self.model is not None:
            self.view.show_counts()

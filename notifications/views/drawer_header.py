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
from microdrop_style.palette_helpers import CHIP_PADDING, css, style_chip, with_alpha
from microdrop_style.panel_theme import icon_button_style, theme_palette
from microdrop_style.typography import CHIP, DRAWER_TITLE, role_font

# Microdrop utils imports.
from microdrop_utils.clamped_label import ElidedLabel

# Local imports.
from ..models.notifications_pane_model import NotificationsPaneModel

#: The drawer's title, and the room (px) between it and the count chip.
TITLE_TEXT = "Notifications"
CHIP_GAP = 8

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

        # Elided, never cut through a glyph; it gives way last.
        self._title = ElidedLabel(TITLE_TEXT, self, title=True)
        self._title.setFont(role_font(DRAWER_TITLE))
        layout.addWidget(self._title)
        layout.addSpacing(CHIP_GAP)

        #: The chip's text in full ("2 new"), and short ("2").
        self._chip_texts = ("", "")

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
            self._chip_texts = (f"{new} new", str(new))

        else:
            self._chip_texts = (str(total), str(total)) if total else ("", "")

        self._fit_chip()
        self.mark_all_read.setEnabled(bool(new or center.unread_count))
        self.clear_all.setEnabled(total > attention)

    def needed_width(self):
        """The width (px) showing the whole title and every button: the
        drawer is never narrower. The chip shortens, then goes, first."""
        margins = self.layout().contentsMargins()
        buttons = sum(button.sizeHint().width() for button in self._buttons())
        spacing = self.layout().spacing() * (len(self._buttons()) + 1)
        title = QtGui.QFontMetrics(self._title.font()).horizontalAdvance(TITLE_TEXT)

        return margins.left() + margins.right() + title + CHIP_GAP + spacing + buttons

    def _fit_chip(self):
        """The chip in full while it fits beside the whole title, short
        when only that fits, else hidden."""
        room = self.width() - self.needed_width() + CHIP_GAP
        full, short = self._chip_texts
        text = ""

        for candidate in (full, short):
            if candidate and self._chip_width(candidate) <= room:
                text = candidate

                break

        self._chip.setText(text)
        self._chip.setVisible(bool(text))

    def _chip_width(self, text):
        metrics = QtGui.QFontMetrics(self._chip.font())

        return metrics.horizontalAdvance(text) + 2 * CHIP_PADDING[1] + 2 + CHIP_GAP

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if event.size().width() != event.oldSize().width():
            self._fit_chip()

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

# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The widgets of the toast stack: a toast (a card on a soft shadow), the
picture of a leaving toast, and the "+N more" pill."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.palette_helpers import css

# Local imports.
from .card import NotificationCard
from .theme import card_border, card_fill, link_color, readable_accent, theme_palette
from .typography import CHIP, role_font

#: Room (px) around a toast's card for its shadow.
SHADOW = 12

#: Opacity of the shadow right under the card.
SHADOW_ALPHA = 0.16


class ToastWidget(QtWidgets.QWidget):
    """A toast card on a soft shadow; reports the pointer over it."""

    hover_changed = QtCore.Signal(bool)

    def __init__(self, entry, parent=None, help_available=True):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(SHADOW, SHADOW - 4, SHADOW, SHADOW + 4)

        self.card = NotificationCard(
            entry, self, toast=True, help_available=help_available
        )
        layout.addWidget(self.card)

    def height_for(self, card_width):
        """The toast's height with a ``card_width`` card."""
        height = self.heightForWidth(card_width + 2 * SHADOW)

        return height if height > 0 else self.sizeHint().height()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        card = QtCore.QRectF(self.card.geometry())

        for step in range(SHADOW, 0, -2):
            alpha = SHADOW_ALPHA * (1 - step / SHADOW) ** 2
            painter.setBrush(QtGui.QColor(0, 0, 0, int(alpha * 255)))
            painter.drawRoundedRect(
                card.adjusted(-step, -step + 3, step, step + 3), 8 + step, 8 + step
            )

    def enterEvent(self, event):
        self.hover_changed.emit(True)

        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_changed.emit(False)

        super().leaveEvent(event)


class ToastGhost(QtWidgets.QWidget):
    """A picture of a leaving toast, drawn into its animated rectangle."""

    def __init__(self, pixmap, parent):
        super().__init__(parent)

        self.pixmap = pixmap
        self.opacity = 1.0

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self.opacity)
        painter.drawPixmap(self.rect(), self.pixmap)


class MorePill(QtWidgets.QPushButton):
    """ "+N more in notifications", above the toasts."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setToolTip("These went straight to the bell. Click to see them.")
        self.restyle()

    def restyle(self):
        palette = theme_palette()

        self.setFont(role_font(CHIP))
        self.setStyleSheet(
            "QPushButton {"
            f" background: {css(card_fill(palette))};"
            f" color: {css(readable_accent(link_color(palette), palette))};"
            f" border: 1px solid {css(card_border(palette))};"
            " border-radius: 13px; padding: 4px 14px; }"
            f" QPushButton:hover {{ background: {css(card_fill(palette, True))}; }}"
        )

    def event(self, event):

        if event.type() == QtCore.QEvent.Type.ApplicationPaletteChange:
            self.restyle()

        return super().event(event)


def lerp_rect(start, end, amount):
    """The rectangle ``amount`` (0-1) of the way from ``start`` to ``end``."""

    def lerp(first, second):
        return int(round(first + (second - first) * amount))

    return QtCore.QRect(
        lerp(start.x(), end.x()),
        lerp(start.y(), end.y()),
        max(lerp(start.width(), end.width()), 1),
        max(lerp(start.height(), end.height()), 1),
    )

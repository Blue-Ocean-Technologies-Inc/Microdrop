# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The card's rows, in the notifications drawer's card language: a problem
is a small rounded card with a severity stripe; a quiet (passed, skipped,
muted) row is flat. Each reads glyph + two or three words."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.palette_helpers import css, icon_font, rounded_path, with_alpha
from microdrop_style.panel_metrics import CARD_RADIUS, STRIPE_WIDTH
from microdrop_style.panel_theme import (
    card_border,
    card_fill,
    icon_button_style,
    muted_text,
    theme_palette,
)
from microdrop_style.typography import BODY_TEXT, META, role_font

# Local imports.
from ..consts import MUTE_ALWAYS, MUTE_RUN
from .pill import status_color
from .view_consts import (
    BADGE_SIZE,
    GLYPH_SIZE,
    ICON_MUTE,
    ICON_UNMUTE,
    ROW_HEIGHT,
    STATUS_BADGES,
    check_glyph,
)

_ALIGN = QtCore.Qt.AlignmentFlag


class StatusGlyph(QtWidgets.QWidget):
    """A check's category glyph, with a small shaped status badge on its
    lower right when the check needs attention."""

    def __init__(self, glyph, color, badge="", badge_color=None, parent=None):
        super().__init__(parent)

        self.setFixedSize(GLYPH_SIZE + 6, GLYPH_SIZE + 4)

        self._glyph, self._color = glyph, color
        self._badge, self._badge_color = badge, badge_color

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        painter.setFont(icon_font(GLYPH_SIZE))
        painter.setPen(self._color)
        painter.drawText(
            QtCore.QRect(0, 0, GLYPH_SIZE, GLYPH_SIZE), _ALIGN.AlignCenter, self._glyph
        )

        if not self._badge:
            return

        size = BADGE_SIZE + 2
        badge = QtCore.QRect(self.width() - size, self.height() - size, size, size)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(card_fill(theme_palette()))
        painter.drawEllipse(badge)

        painter.setFont(icon_font(BADGE_SIZE))
        painter.setPen(self._badge_color)
        painter.drawText(badge, _ALIGN.AlignCenter, self._badge)


class CheckRow(QtWidgets.QWidget):
    """One check on one line. ``card`` rows (problems) paint the drawer's
    card surface and stripe; others are flat."""

    #: Mute (check, "run" | "always") / unmute (check).
    mute_requested = QtCore.Signal(object, str)
    unmute_requested = QtCore.Signal(object)

    def __init__(self, check, muted="", card=False, parent=None):
        super().__init__(parent)

        self.check = check
        self.muted = muted
        self.card = card
        self._hovered = False

        self.setFixedHeight(ROW_HEIGHT)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip(check.tooltip or check.label)

        self._build(theme_palette())

    def _build(self, palette):
        layout = QtWidgets.QHBoxLayout(self)
        left = STRIPE_WIDTH + 6 if self.card else 6
        layout.setContentsMargins(left, 0, 4, 0)
        layout.setSpacing(6)

        layout.addWidget(self._glyph(palette), 0, _ALIGN.AlignVCenter)

        label = QtWidgets.QLabel(self._label_text())
        font = role_font(BODY_TEXT)
        font.setWeight(
            QtGui.QFont.Weight.DemiBold if self.card else QtGui.QFont.Weight.Normal
        )
        label.setFont(font)

        if not self.card:
            label.setStyleSheet(f"color: {css(muted_text(palette))};")

        detail = QtWidgets.QLabel(self._detail_text())
        detail.setFont(role_font(META))
        detail.setStyleSheet(f"color: {css(muted_text(palette))};")
        detail.setAlignment(_ALIGN.AlignRight | _ALIGN.AlignVCenter)
        detail.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        layout.addWidget(label)
        layout.addWidget(detail, 1)

        mute_button = self._mute_button(palette)

        if mute_button is not None:
            layout.addWidget(mute_button)

    def _glyph(self, palette):
        status = self.check.status

        if self.muted:
            return StatusGlyph(
                check_glyph(self.check.id),
                muted_text(palette),
                ICON_MUTE,
                muted_text(palette),
            )

        if status in ("warn", "fail"):
            color = status_color(status, palette)

            return StatusGlyph(
                check_glyph(self.check.id), color, STATUS_BADGES[status], color
            )

        if status == "skip":
            grey = muted_text(palette)

            return StatusGlyph(
                check_glyph(self.check.id), grey, STATUS_BADGES[status], grey
            )

        return StatusGlyph(check_glyph(self.check.id), muted_text(palette))

    def _label_text(self):
        """The problem phrase on a problem row, else the neutral label."""
        if self.check.status in ("warn", "fail") and not self.muted:
            return self.check.problem or self.check.label

        return self.check.label

    def _detail_text(self):
        if self.muted:
            scope = "this run" if self.muted == MUTE_RUN else "always"

            return f"Muted, {scope}"

        # A skip's detail says why it was not checked; its tooltip, in full.
        return self.check.detail

    def _mute_button(self, palette):
        """Unmute on a muted row; a mute on a warning; nothing otherwise
        (blocking rows can never be ignored)."""
        if not self.muted and self.check.status != "warn":
            return None

        button = QtWidgets.QToolButton()
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(icon_button_style(palette, 15))
        check = self.check

        if self.muted:
            button.setText(ICON_UNMUTE)
            button.setToolTip("Unmute")
            button.clicked.connect(lambda: self.unmute_requested.emit(check))

        elif check.mutable_always:
            button.setText(ICON_MUTE)
            button.setToolTip("Ignore…")
            button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)

            menu = QtWidgets.QMenu(button)
            menu.addAction(
                "This run", lambda: self.mute_requested.emit(check, MUTE_RUN)
            )
            menu.addAction(
                "Always", lambda: self.mute_requested.emit(check, MUTE_ALWAYS)
            )
            button.setMenu(menu)

        else:
            button.setText(ICON_MUTE)
            button.setToolTip("Ignore for this run")
            button.clicked.connect(lambda: self.mute_requested.emit(check, MUTE_RUN))

        return button

    def event(self, event):
        if event.type() in (
            QtCore.QEvent.Type.HoverEnter,
            QtCore.QEvent.Type.HoverLeave,
        ):
            self._hovered = event.type() == QtCore.QEvent.Type.HoverEnter
            self.update()

        return super().event(event)

    def paintEvent(self, event):
        palette = theme_palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = rounded_path(rect, CARD_RADIUS)

        if self.card:
            painter.setPen(QtGui.QPen(card_border(palette), 1))
            painter.setBrush(card_fill(palette, self._hovered))
            painter.drawPath(path)

            painter.setClipPath(path)
            painter.fillRect(
                QtCore.QRect(0, 0, STRIPE_WIDTH, self.height()),
                status_color(self.check.status, palette, on_card=False),
            )

        elif self._hovered:
            text = palette.color(QtGui.QPalette.ColorRole.Text)

            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(with_alpha(text, 0.06))
            painter.drawPath(path)


def group_label(category, palette):
    """A small-caps group label for the expanded list."""
    label = QtWidgets.QLabel(category.upper())
    font = role_font(META, QtGui.QFont.Weight.DemiBold)
    font.setPointSizeF(font.pointSizeF() - 1)
    font.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 112)

    label.setFont(font)
    label.setFixedHeight(ROW_HEIGHT - 8)
    label.setContentsMargins(6, 0, 0, 0)
    label.setStyleSheet(f"color: {css(muted_text(palette))};")

    return label

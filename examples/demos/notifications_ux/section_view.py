# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A drawer section's header, painted::

    (◉) Section title  [ 3 new ]                         ⌄

Its glyph and colour come from the section's SectionStyle, like the
colour-coded sections of a phone's news app; its chevron turns as the
section opens. Runs standalone::

    header = SectionHeader(DEFAULT_SECTION_STYLE)
    header.show_section("Plugins", "13 loaded", True, False)
    header.show()
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_EXPAND_MORE

# Local imports.
from .typography import CHIP, SECTION_TITLE, role_font
from .ux_consts import (
    NEWS_LOGO_HEIGHT,
    SECTION_ANIMATION_MS,
)
from .view_styles import (
    icon_font,
    muted_text,
    readable_accent,
    scaled_logo,
    with_alpha,
)

#: Height (px) of a section header, and of its glyph's disc.
HEADER_HEIGHT = 40
DISC_SIZE = 26

_ALIGN = QtCore.Qt.AlignmentFlag
_LEFT_MIDDLE = _ALIGN.AlignLeft | _ALIGN.AlignVCenter


class SectionHeader(QtWidgets.QAbstractButton):
    """Glyph disc, title, summary chip and a chevron that turns as the
    section opens. Painted, so it costs one widget."""

    def __init__(self, style, parent=None):
        super().__init__(parent)

        self.style_ = style
        self.title = ""
        self.summary = ""

        #: Drawn opaque with a rule under it, as the pinned copy at the top
        #: of a scrolling column.
        self.pinned = False

        #: 0 collapsed, 1 expanded; animated between.
        self._openness = 1.0

        self.setFixedHeight(HEADER_HEIGHT)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed
        )

        self._turn = QtCore.QVariantAnimation(self)
        self._turn.setDuration(SECTION_ANIMATION_MS)
        self._turn.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._turn.valueChanged.connect(self._set_openness)

    def show_section(self, title, summary, expanded, animate):
        """Show ``title`` and ``summary``, the chevron turned for
        ``expanded``."""
        self.title, self.summary = title, summary
        target = 1.0 if expanded else 0.0
        self.setToolTip(f"{'Collapse' if expanded else 'Expand'} {title}")

        if animate and target != self._openness:
            self._turn.stop()
            self._turn.setStartValue(self._openness)
            self._turn.setEndValue(target)
            self._turn.start()

        else:
            self._openness = target

        self.update()

    def _set_openness(self, value):
        self._openness = value
        self.update()

    def sizeHint(self):
        return QtCore.QSize(200, self.height())

    def paintEvent(self, event):
        palette = self.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        text_color = palette.color(QtGui.QPalette.ColorRole.Text)
        accent = QtGui.QColor(self.style_.accent)
        readable = readable_accent(accent, palette)
        rect = self.rect().adjusted(0, 3, 0, -3)

        if self.pinned:
            painter.fillRect(
                self.rect(), palette.color(QtGui.QPalette.ColorRole.Window)
            )
            painter.setPen(with_alpha(text_color, 0.12))
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        if self.underMouse():
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(with_alpha(text_color, 0.06))
            painter.drawRoundedRect(QtCore.QRectF(rect), 7, 7)

        # A brand mark at its own width, or the glyph on a tinted disc.
        disc = QtCore.QRectF(6, (self.height() - DISC_SIZE) / 2, DISC_SIZE, DISC_SIZE)

        if self.style_.logo:
            logo = scaled_logo(
                self.style_.logo, NEWS_LOGO_HEIGHT, self.devicePixelRatioF()
            )
            size = logo.deviceIndependentSize()
            disc = QtCore.QRectF(
                6, (self.height() - size.height()) / 2, size.width(), size.height()
            )
            painter.drawPixmap(disc.topLeft(), logo)

        else:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(with_alpha(accent, 0.18))
            painter.drawEllipse(disc)
            painter.setFont(icon_font(17))
            painter.setPen(readable)
            painter.drawText(disc, _ALIGN.AlignCenter, self.style_.glyph)

        # The chevron, turned from pointing right (collapsed) to down.
        chevron = QtCore.QRectF(self.width() - 30, 0, 24, self.height())
        painter.save()
        painter.translate(chevron.center())
        painter.rotate(-90 * (1 - self._openness))
        painter.setFont(icon_font(20))
        painter.setPen(muted_text(palette))
        painter.drawText(
            QtCore.QRectF(-12, -12, 24, 24), _ALIGN.AlignCenter, ICON_EXPAND_MORE
        )
        painter.restore()

        # The title, then the summary chip as room allows.
        title_font = role_font(SECTION_TITLE)
        metrics = QtGui.QFontMetrics(title_font)
        left = int(disc.right()) + 10
        room = int(chevron.left()) - 8 - left
        title = metrics.elidedText(self.title, QtCore.Qt.TextElideMode.ElideRight, room)
        title_width = metrics.horizontalAdvance(title)

        painter.setFont(title_font)
        painter.setPen(text_color)
        painter.drawText(
            QtCore.QRect(left, 0, title_width + 2, self.height()), _LEFT_MIDDLE, title
        )

        chip_room = room - title_width - 10

        if self.summary and chip_room > 28:
            self._paint_chip(
                painter, left + title_width + 10, chip_room, accent, readable
            )

    def _paint_chip(self, painter, left, room, accent, readable):
        font = role_font(CHIP)
        metrics = QtGui.QFontMetrics(font)
        text = metrics.elidedText(
            self.summary, QtCore.Qt.TextElideMode.ElideRight, room - 16
        )
        width = metrics.horizontalAdvance(text) + 16
        height = metrics.height() + 4
        chip = QtCore.QRectF(left, (self.height() - height) / 2, width, height)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(accent, 0.16))
        painter.drawRoundedRect(chip, height / 2, height / 2)
        painter.setFont(font)
        painter.setPen(readable)
        painter.drawText(chip, _ALIGN.AlignCenter, text)

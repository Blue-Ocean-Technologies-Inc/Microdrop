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

Its glyph (or brand mark) and accent are the section's own; its chevron
turns as the section opens. Runs standalone::

    header = SectionHeader()
    header.show_section(NotificationSection(title="Plugins"), True, False)
    header.show()
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_EXPAND_MORE
from microdrop_style.palette_helpers import icon_font, scaled_logo, with_alpha

# Local imports.
from .theme import accent_of, chip_text, chip_tint, disc_tint, muted_text, theme_palette
from .typography import CHIP, SECTION_TITLE, role_font
from .view_consts import SECTION_ANIMATION_MS, SECTION_LOGO_HEIGHT

#: Height (px) of a section header, and of its glyph's disc.
HEADER_HEIGHT = 40
DISC_SIZE = 26

_ALIGN = QtCore.Qt.AlignmentFlag
_LEFT_MIDDLE = _ALIGN.AlignLeft | _ALIGN.AlignVCenter
_ELIDE = QtCore.Qt.TextElideMode.ElideRight


class SectionHeader(QtWidgets.QAbstractButton):
    """Glyph disc, title, summary chip and a chevron that turns as the
    section opens. Painted, so it costs one widget."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.title = ""
        self.summary = ""
        self.glyph = ""
        self.accent = ("#000000", "#FFFFFF")
        self.logo = ""

        #: Drawn opaque with a rule under it, as the pinned copy at the top
        #: of a scrolling column.
        self.pinned = False

        #: 0 collapsed, 1 expanded; animated between. The animation is made
        #: on the first turn.
        self._openness = 1.0
        self._turn = None

        self.setFixedHeight(HEADER_HEIGHT)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed
        )

    def show_section(self, section, expanded, animate):
        """Show ``section``'s title, summary and look, the chevron turned for
        ``expanded``."""
        self.title, self.summary = section.title, section.summary
        self.glyph, self.accent, self.logo = section.glyph, section.accent, section.logo
        target = 1.0 if expanded else 0.0

        self.setToolTip(f"{'Collapse' if expanded else 'Expand'} {self.title}")

        if animate and target != self._openness:
            self._animate_to(target)

        else:
            self._openness = target

        self.update()

    def sizeHint(self):
        return QtCore.QSize(200, self.height())

    def _animate_to(self, target):

        if self._turn is None:
            self._turn = QtCore.QVariantAnimation(self)
            self._turn.setDuration(SECTION_ANIMATION_MS)
            self._turn.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
            self._turn.valueChanged.connect(self._set_openness)

        self._turn.stop()
        self._turn.setStartValue(self._openness)
        self._turn.setEndValue(target)
        self._turn.start()

    def _set_openness(self, value):
        self._openness = value
        self.update()

    def paintEvent(self, event):
        palette = theme_palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        text_color = palette.color(QtGui.QPalette.ColorRole.Text)
        accent = accent_of(self.accent, palette)
        readable = chip_text(accent, palette)
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

        disc = self._paint_mark(painter, accent, readable, palette)

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
        title = metrics.elidedText(self.title, _ELIDE, room)
        title_width = metrics.horizontalAdvance(title)

        painter.setFont(title_font)
        painter.setPen(text_color)
        painter.drawText(
            QtCore.QRect(left, 0, title_width + 2, self.height()), _LEFT_MIDDLE, title
        )

        chip_room = room - title_width - 10

        if self.summary and chip_room > 28:
            chip_left = left + title_width + 10
            self._paint_chip(painter, chip_left, chip_room, accent, readable, palette)

    def _paint_mark(self, painter, accent, readable, palette):
        """A brand mark at its own width, or the glyph on a tinted disc;
        returns where it went."""
        top = (self.height() - DISC_SIZE) / 2

        if self.logo:
            logo = scaled_logo(self.logo, SECTION_LOGO_HEIGHT, self.devicePixelRatioF())
            size = logo.deviceIndependentSize()
            mark = QtCore.QRectF(
                6, (self.height() - size.height()) / 2, size.width(), size.height()
            )
            painter.drawPixmap(mark.topLeft(), logo)

            return mark

        disc = QtCore.QRectF(6, top, DISC_SIZE, DISC_SIZE)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(accent, disc_tint(palette)))
        painter.drawEllipse(disc)
        painter.setFont(icon_font(17))
        painter.setPen(readable)
        painter.drawText(disc, _ALIGN.AlignCenter, self.glyph)

        return disc

    def _paint_chip(self, painter, left, room, accent, readable, palette):
        font = role_font(CHIP)
        metrics = QtGui.QFontMetrics(font)
        text = metrics.elidedText(self.summary, _ELIDE, room - 16)
        width = metrics.horizontalAdvance(text) + 16
        height = metrics.height() + 4
        chip = QtCore.QRectF(left, (self.height() - height) / 2, width, height)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(accent, chip_tint(palette)))
        painter.drawRoundedRect(chip, height / 2, height / 2)
        painter.setFont(font)
        painter.setPen(readable)
        painter.drawText(chip, _ALIGN.AlignCenter, text)

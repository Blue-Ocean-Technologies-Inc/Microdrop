# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Paint each notification as a card, and hand its clicks on as signals.

Cards are painted, not built from widgets, so hundreds of them cost no more
than the rows on screen. Only an expanded card gets a widget: a read-only
text viewer (selectable; tracebacks monospace and unwrapped) opened as the
row's persistent editor. Colours come from the palette, so cards follow the
light and dark themes; only the severity colours are fixed.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_CLOSE, ICON_EXPAND_LESS, ICON_EXPAND_MORE

# Local imports.
from ..consts import SEVERITY_COLORS, SEVERITY_GLYPHS
from .card_layout import ACCENT_WIDTH, layout_card
from .formatting import (
    format_exact_time,
    format_meta,
    format_preview,
    format_tooltip,
)
from .notification_list_model import ENTRY_ROLE

#: Pixel size of a card's severity glyph, and of its small glyphs.
GLYPH_PIXEL_SIZE = 22
SMALL_GLYPH_PIXEL_SIZE = 16

#: Corner radius of cards and pills.
CORNER_RADIUS = 6

_ROLE = QtGui.QPalette.ColorRole
_ALIGN = QtCore.Qt.AlignmentFlag
_LEFT_MIDDLE = _ALIGN.AlignLeft | _ALIGN.AlignVCenter


def _icon_font(pixel_size):
    font = QtGui.QFont(ICON_FONT_FAMILY)
    font.setPixelSize(pixel_size)

    return font


class NotificationDelegate(QtWidgets.QStyledItemDelegate):
    """Paints notification cards; emits the entry a click acts on."""

    #: The entry's dismiss cross was clicked.
    dismiss_requested = QtCore.Signal(object)

    #: The entry's action button was clicked.
    action_requested = QtCore.Signal(object)

    #: The rest of a card with a detail was clicked: show or hide it.
    expand_toggled = QtCore.Signal(object)

    def __init__(self, view):
        super().__init__(view)

        self._view = view
        self._glyph_font = _icon_font(GLYPH_PIXEL_SIZE)
        self._small_glyph_font = _icon_font(SMALL_GLYPH_PIXEL_SIZE)
        self._monospace_font = QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.SystemFont.FixedFont
        )

    def layout(self, rect, entry):
        """The card layout of ``entry`` in the row ``rect``."""
        return layout_card(
            rect, entry, self._view.font(), self._monospace_font, GLYPH_PIXEL_SIZE
        )

    # ------------------------------------------------------------------ #
    # Painting and size                                                   #
    # ------------------------------------------------------------------ #

    def sizeHint(self, option, index):
        entry = index.data(ENTRY_ROLE)
        width = self._view.viewport().width()
        card = self.layout(QtCore.QRect(0, 0, width, 0), entry)

        return QtCore.QSize(width, card.height)

    def paint(self, painter, option, index):
        entry = index.data(ENTRY_ROLE)
        card = self.layout(option.rect, entry)
        palette = option.palette
        severity_color = QtGui.QColor(SEVERITY_COLORS[entry.severity])
        muted = palette.color(_ROLE.PlaceholderText)
        hovered = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        self._paint_card(painter, card.card, palette, severity_color, hovered)

        painter.setFont(self._glyph_font)
        painter.setPen(severity_color)
        painter.drawText(
            card.glyph, _ALIGN.AlignCenter, SEVERITY_GLYPHS[entry.severity]
        )

        font = self._view.font()
        title_font = QtGui.QFont(font)
        title_font.setBold(entry.unread)

        self._draw_elided(
            painter, card.title, entry.title, title_font, palette.color(_ROLE.Text)
        )
        self._draw_elided(painter, card.time, card.time_text, font, muted)
        self._draw_glyph(painter, card.dismiss, ICON_CLOSE, muted)

        if card.count is not None:
            self._paint_pill(painter, card.count, f"×{entry.count}", severity_color)

        self._draw_elided(painter, card.meta, format_meta(entry), font, muted)

        if card.action is not None:
            highlight = palette.color(_ROLE.Highlight)
            self._paint_pill(painter, card.action, entry.action.label, highlight)

        if card.chevron is not None:
            glyph = ICON_EXPAND_LESS if entry.expanded else ICON_EXPAND_MORE
            self._draw_glyph(painter, card.chevron, glyph, muted)

        if card.preview is not None:
            preview = format_preview(entry)
            self._draw_elided(painter, card.preview, preview, font, muted)

        painter.restore()

    def _paint_card(self, painter, rect, palette, severity_color, hovered):
        """The card's rounded body, with the severity strip clipped to it."""
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), CORNER_RADIUS, CORNER_RADIUS)
        fill = palette.color(_ROLE.AlternateBase if hovered else _ROLE.Base)

        painter.setPen(palette.color(_ROLE.Mid))
        painter.setBrush(fill)
        painter.drawPath(path)

        painter.save()
        painter.setClipPath(path)
        painter.fillRect(
            QtCore.QRect(rect.left(), rect.top(), ACCENT_WIDTH, rect.height()),
            severity_color,
        )
        painter.restore()

    def _paint_pill(self, painter, rect, text, color):
        """A rounded outline in ``color`` with ``text`` centred in it."""
        painter.setPen(color)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QtCore.QRectF(rect), CORNER_RADIUS, CORNER_RADIUS)
        painter.setFont(self._view.font())
        painter.drawText(rect, _ALIGN.AlignCenter, text)

    def _draw_glyph(self, painter, rect, glyph, color):
        painter.setFont(self._small_glyph_font)
        painter.setPen(color)
        painter.drawText(rect, _ALIGN.AlignCenter, glyph)

    @staticmethod
    def _draw_elided(painter, rect, text, font, color):
        metrics = QtGui.QFontMetrics(font)
        elided = metrics.elidedText(
            text, QtCore.Qt.TextElideMode.ElideRight, rect.width()
        )

        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, _LEFT_MIDDLE, elided)

    # ------------------------------------------------------------------ #
    # Clicks and tooltips                                                 #
    # ------------------------------------------------------------------ #

    def editorEvent(self, event, model, option, index):
        """Route a left click on a card to the part under it."""
        released = event.type() == QtCore.QEvent.Type.MouseButtonRelease

        if not released or event.button() != QtCore.Qt.MouseButton.LeftButton:
            return False

        entry = index.data(ENTRY_ROLE)
        card = self.layout(option.rect, entry)
        position = event.position().toPoint()

        if card.dismiss.contains(position):
            self.dismiss_requested.emit(entry)

        elif card.action is not None and card.action.contains(position):
            self.action_requested.emit(entry)

        elif entry.detail:
            self.expand_toggled.emit(entry)

        else:
            return False

        return True

    def helpEvent(self, event, view, option, index):
        """Say when the entry occurred, how often and who posted it."""

        if event.type() != QtCore.QEvent.Type.ToolTip or not index.isValid():
            return super().helpEvent(event, view, option, index)

        entry = index.data(ENTRY_ROLE)
        card = self.layout(option.rect, entry)
        position = event.pos()

        if card.dismiss.contains(position):
            text = "Dismiss"

        elif card.time.contains(position):
            text = format_exact_time(entry.last_seen)

        elif card.action is not None and card.action.contains(position):
            text = entry.action.label

        else:
            text = format_tooltip(entry)

        QtWidgets.QToolTip.showText(event.globalPos(), text, view)

        return True

    # ------------------------------------------------------------------ #
    # The expanded detail                                                 #
    # ------------------------------------------------------------------ #

    def createEditor(self, parent, option, index):
        entry = index.data(ENTRY_ROLE)
        viewer = QtWidgets.QPlainTextEdit(parent)

        viewer.setReadOnly(True)
        viewer.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        viewer.setPlainText(entry.detail)

        if entry.monospace_detail:
            viewer.setFont(self._monospace_font)
            viewer.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)

        return viewer

    def setEditorData(self, editor, index):
        detail = index.data(ENTRY_ROLE).detail

        if editor.toPlainText() != detail:
            editor.setPlainText(detail)

    def setModelData(self, editor, model, index):
        """The detail is read-only: nothing goes back."""

    def updateEditorGeometry(self, editor, option, index):
        card = self.layout(option.rect, index.data(ENTRY_ROLE))

        if card.detail is not None:
            editor.setGeometry(card.detail)

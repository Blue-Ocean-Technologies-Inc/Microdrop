# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""The widgets a feed post card is built from: an elided line, the card's
rounded frame, a thumbnail, the lead card's two-picture pair, and the
picture preview window."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Local imports.
from .card_style import (
    CORNER_RADIUS,
    GRID,
    PAIR_ASPECT,
    PAIR_MIN_WIDTH,
    PREVIEW_SCREEN_SHARE,
    THUMBNAIL_SIZE,
    cropped,
    fitted,
    is_dark,
    picture_pair_cells,
    placeholder_fill,
    rounded_rect_path,
)

_ROLE = QtGui.QPalette.ColorRole
_ALIGN = QtCore.Qt.AlignmentFlag
_PALETTE_EVENTS = (
    QtCore.QEvent.Type.PaletteChange,
    QtCore.QEvent.Type.ApplicationPaletteChange,
)


class ElidedLine(QtWidgets.QWidget):
    """Word-wrapped text in at most ``max_lines`` lines, the last elided;
    as tall as the lines it takes at its width, in its foreground role."""

    def __init__(self, text, max_lines, parent=None):
        super().__init__(parent)

        self._text = text
        self._max_lines = max_lines
        self.setToolTip(text)
        policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        lines = len(self._lines(width))

        return lines * QtGui.QFontMetrics(self.font()).lineSpacing()

    def sizeHint(self):
        return QtCore.QSize(20 * GRID, self.heightForWidth(20 * GRID))

    def minimumSizeHint(self):
        return QtCore.QSize(4 * GRID, QtGui.QFontMetrics(self.font()).lineSpacing())

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))
        spacing = QtGui.QFontMetrics(self.font()).lineSpacing()
        flags = _ALIGN.AlignLeft | _ALIGN.AlignVCenter

        for number, line in enumerate(self._lines(self.width())):
            rect = QtCore.QRect(0, number * spacing, self.width(), spacing)
            painter.drawText(rect, flags, line)

    def _lines(self, width):
        """The text's lines at ``width``, at most ``max_lines``, the last
        elided if more would follow."""
        width = max(width, 1)
        layout = QtGui.QTextLayout(self._text, self.font())
        starts = []

        layout.beginLayout()

        while len(starts) < self._max_lines:
            line = layout.createLine()

            if not line.isValid():
                break

            line.setLineWidth(width)
            starts.append((line.textStart(), line.textLength()))

        overflow = layout.createLine().isValid()
        layout.endLayout()

        lines = [self._text[start : start + length].strip() for start, length in starts]

        if overflow and lines:
            metrics = QtGui.QFontMetrics(self.font())
            rest = self._text[starts[-1][0] :].strip()
            lines[-1] = metrics.elidedText(
                rest, QtCore.Qt.TextElideMode.ElideRight, width
            )

        return lines


class CardFrame(QtWidgets.QFrame):
    """A rounded card with a hover state and an optional banner on top,
    painted from its palette."""

    clicked = QtCore.Signal()
    resized = QtCore.Signal()
    palette_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover)
        self._hovered = False

        # Its height is its height for its width, every pass: a Maximum
        # policy capped it at the height for its previous width, so a card
        # narrowed (its pictures stacking) was cut off below the first.
        # Its width is the column's: a layout measures a child's height at
        # no less than its minimum width, and a card's rows can ask more
        # than the drawer's narrowest column, measuring it short (side by
        # side) while it is drawn narrow (stacked).
        policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        #: The banner: None for none, a QPixmap, or "loading".
        self.banner = None
        self.banner_height = 0

    def paintEvent(self, event):
        palette = self.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        body = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fill = palette.color(_ROLE.Base)

        if self._hovered:
            fill = fill.lighter(118) if is_dark(palette) else fill.darker(103)

        painter.setPen(palette.color(_ROLE.Mid))
        painter.setBrush(fill)
        painter.drawRoundedRect(body, CORNER_RADIUS, CORNER_RADIUS)

        if self.banner is None or not self.banner_height:
            return

        banner_rect = QtCore.QRect(0, 0, self.width(), self.banner_height)
        painter.setClipPath(rounded_rect_path(body))

        if self.banner == "loading":
            painter.fillRect(banner_rect, placeholder_fill(palette))

        else:
            painter.drawPixmap(banner_rect, self.banner)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()

        super().mouseReleaseEvent(event)

    def sizeHint(self):
        """Its height at its current width: a Maximum height policy caps it
        at the hint, which must follow pictures and text rewrapping."""
        hint = super().sizeHint()

        if self.width() > 0 and self.hasHeightForWidth():
            hint.setHeight(self.heightForWidth(self.width()))

        return hint

    def resizeEvent(self, event):
        super().resizeEvent(event)

        # A new width is a new height: have the layout ask again.
        if event.size().width() != event.oldSize().width():
            self.updateGeometry()

        self.resized.emit()

    def changeEvent(self, event):
        super().changeEvent(event)

        if event.type() in _PALETTE_EVENTS:
            self.palette_changed.emit()


class Thumbnail(QtWidgets.QWidget):
    """A small rounded muted shape; the picture, once loaded, centred on it
    whole, so a picture of another shape is letterboxed, never cropped."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.pixmap = None
        self.setFixedSize(*THUMBNAIL_SIZE)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setClipPath(rounded_rect_path(self.rect(), CORNER_RADIUS - 2))
        painter.fillRect(self.rect(), placeholder_fill(self.palette()))

        if self.pixmap is None:
            return

        target = QtWidgets.QStyle.alignedRect(
            QtCore.Qt.LayoutDirection.LeftToRight,
            _ALIGN.AlignCenter,
            self.pixmap.deviceIndependentSize().toSize(),
            self.rect(),
        )
        painter.drawPixmap(target, self.pixmap)


class PicturePair(QtWidgets.QWidget):
    """Two captioned pictures, side by side at equal height, or stacked when
    narrow (see ``picture_pair_cells``), each filling its cell edge to edge,
    cropped as little as the cell needs. A click on one emits
    ``picture_clicked`` with its index, and goes no further."""

    picture_clicked = QtCore.Signal(int)

    def __init__(self, captions, alts, parent=None):
        super().__init__(parent)

        self.captions = captions
        self.alts = alts

        #: The loaded pictures, as loaded: every crop is made from these.
        self.pixmaps = [None] * len(captions)

        #: The pictures' sizes known before they load (QSize or None), so
        #: the cells have their final shape from the start.
        self.sizes = [None] * len(captions)

        #: Crops made for the current cells, by index; dropped on resize.
        self._crops = {}

        # Its height follows its width (heightForWidth); never fixed.
        policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def set_picture(self, index, pixmap):
        """Show ``pixmap`` as picture ``index``: its aspect sets the cells,
        so the pair's height may change."""
        self.pixmaps[index] = pixmap
        self._crops = {}
        self.updateGeometry()
        self.update()

    def _aspects(self):
        """Each picture's width over height: as loaded, else as its known
        size says, else PAIR_ASPECT."""
        aspects = []

        for pixmap, known in zip(self.pixmaps[:2], self.sizes[:2]):
            size = pixmap.deviceIndependentSize() if pixmap is not None else known
            aspect = size.width() / max(size.height(), 1) if size else PAIR_ASPECT
            aspects.append(aspect or PAIR_ASPECT)

        return tuple(aspects)

    def _caption_height(self):
        """Room for a caption line beneath each picture; none without any."""

        if not any(self.captions):
            return 0

        return QtGui.QFontMetrics(self.font()).height() + GRID // 2

    def _rects(self, width):
        """Where each picture goes at ``width``."""
        cells, _height = picture_pair_cells(
            width, self._caption_height(), self._aspects()
        )

        return [QtCore.QRect(*cell) for cell in cells]

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return picture_pair_cells(width, self._caption_height(), self._aspects())[1]

    def sizeHint(self):
        width = self.width() if self.width() > 0 else PAIR_MIN_WIDTH

        return QtCore.QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self):
        return QtCore.QSize(0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self._crops = {}

    def _crop(self, index, rect):
        """Picture ``index`` for ``rect``, made once per size from the loaded
        picture, sharp at the device pixel ratio, filling it (cropped as
        little as it needs)."""
        crop = self._crops.get(index)

        if crop is not None:
            return crop

        ratio = self.devicePixelRatioF()
        crop = cropped(self.pixmaps[index], rect.width(), rect.height(), ratio)
        self._crops[index] = crop

        return crop

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        font = self.font()

        painter.setFont(font)

        for index, (rect, caption) in enumerate(
            zip(self._rects(self.width()), self.captions)
        ):
            painter.save()
            painter.setClipPath(rounded_rect_path(rect, CORNER_RADIUS - 2))

            if self.pixmaps[index] is None:
                painter.fillRect(rect, placeholder_fill(palette))

            else:
                painter.drawPixmap(rect, self._crop(index, rect))

            painter.restore()

            text = QtCore.QRect(
                rect.left(),
                rect.bottom() + 1 + GRID // 2,
                rect.width(),
                self._caption_height(),
            )
            painter.setPen(palette.color(_ROLE.PlaceholderText))
            painter.drawText(text, _ALIGN.AlignLeft | _ALIGN.AlignTop, caption)

    def _index_at(self, position):

        for index, rect in enumerate(self._rects(self.width())):
            if rect.contains(position):
                return index

        return None

    def event(self, event):

        if event.type() == QtCore.QEvent.Type.ToolTip:
            index = self._index_at(event.pos())

            if index is not None and self.alts[index]:
                QtWidgets.QToolTip.showText(event.globalPos(), self.alts[index], self)

            else:
                QtWidgets.QToolTip.hideText()

            return True

        return super().event(event)

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        index = self._index_at(event.position().toPoint())

        if event.button() == QtCore.Qt.MouseButton.LeftButton and index is not None:
            self.picture_clicked.emit(index)

        event.accept()


def show_picture_preview(pixmap, caption, parent):
    """``pixmap`` larger, in a small window closed by a click or Esc."""
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle(caption or "Picture")
    dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)

    screen = (parent.screen() if parent is not None else None) or (
        QtGui.QGuiApplication.primaryScreen()
    )
    room = screen.availableGeometry().size() * PREVIEW_SCREEN_SHARE
    label = QtWidgets.QLabel(dialog)
    label.setPixmap(
        fitted(pixmap, room.width(), room.height(), dialog.devicePixelRatioF())
    )
    label.mouseReleaseEvent = lambda event: dialog.accept()

    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label)
    dialog.show()

    return dialog

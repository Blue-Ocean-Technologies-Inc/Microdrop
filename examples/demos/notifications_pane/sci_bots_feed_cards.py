# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A feed post as a card: a lead card (picture as a banner on top, large
title) or a compact row (title, meta line, small picture at the right).

News, not alerts: no severity strip; the kind is a small label in the
group's accent. Cards are painted from their palette, so they follow the
theme, also a preview's; spacing is on an 8-pixel grid. Clicking a card
that has a summary shows or hides it; a compact row without one is itself
the post's link. Links go to the controller.
"""

# Standard library imports.
import re
from functools import partial
from html import escape

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Bool, Dict, HasTraits, Instance, Int, List, Str, observe

# Local imports.
from .sci_bots_feed_model import (
    ORIGIN_PUSHED,
    FeedPost,
    format_post_date,
    summary_teaser,
)
from .sci_bots_feed_thumbnails import thumbnail_loader

#: The grid all spacing is a multiple of.
GRID = 8

#: Corner radius of cards, pictures and banners.
CORNER_RADIUS = 10

#: A lead card's banner: at most this tall; this tall while it loads.
BANNER_MAX_HEIGHT = 168
BANNER_LOADING_HEIGHT = 112

#: A compact row's picture box; the picture fits inside it whole.
THUMBNAIL_SIZE = (11 * GRID, 7 * GRID)

#: A lead card's two pictures: each centre-cropped to this aspect (width
#: over height) so they stand at equal height, side by side unless the
#: card is narrower than PAIR_MIN_WIDTH, then stacked.
PAIR_ASPECT = 4 / 3
PAIR_MIN_WIDTH = 35 * GRID

#: A picture's preview: at most this share of its screen.
PREVIEW_SCREEN_SHARE = 0.8

#: Lines a title takes before it is elided: lead, compact.
LEAD_TITLE_LINES = 3
COMPACT_TITLE_LINES = 2

#: Lines of the summary shown while a lead card is collapsed.
SUMMARY_COLLAPSED_LINES = 3

#: Lines of a release' lead card shown collapsed: its first few features.
RELEASE_COLLAPSED_LINES = 6

#: How much of the text colour a placeholder fill takes, and of the accent
#: a release's scope tag takes, over the card colour.
PLACEHOLDER_TINT = 0.07
TAG_TINT = 0.14

#: Points added to the base font: lead title, compact title, small text.
LEAD_TITLE_POINTS = 3
COMPACT_TITLE_POINTS = 1
SMALL_POINTS = -1

#: How each kind is named on its card.
KIND_LABELS = {
    "announcement": "Announcement",
    "product": "Product",
    "newsletter": "Newsletter",
    "post": "Post",
    "release": "Release",
}

#: The hrefs of the card's own links.
READ_MORE_HREF = "#read-more"
REMOVE_HREF = "#remove"

#: A release summary's "scope: text" item, and its "and N more" line.
_SCOPED_ITEM = re.compile(r"<li>([\w.-]+): ")
_MORE_LINE = re.compile(r"<p>(and \d+ more)</p>")
_INTRO_LINE = re.compile(r"<p>(New:|Fixes:)</p>")

_ROLE = QtGui.QPalette.ColorRole
_ALIGN = QtCore.Qt.AlignmentFlag
_PALETTE_EVENTS = (
    QtCore.QEvent.Type.PaletteChange,
    QtCore.QEvent.Type.ApplicationPaletteChange,
)


def is_dark(palette):
    """Whether ``palette`` is a dark theme's."""
    return palette.color(_ROLE.Base).lightness() < 128


def accent_color(spec, palette):
    """``spec``'s accent for the theme of ``palette``."""
    light, dark = spec.accent

    return QtGui.QColor(dark if is_dark(palette) else light)


def scaled_font(widget, points, bold=False):
    font = QtGui.QFont(widget.font())
    font.setPointSizeF(max(font.pointSizeF() + points, 6))
    font.setBold(bold)

    return font


def blend(base, over, amount):
    """``over`` laid over ``base`` at ``amount`` (0 to 1), as a QColor."""
    return QtGui.QColor(
        *(
            round(low + (high - low) * amount)
            for low, high in zip(base.getRgb()[:3], over.getRgb()[:3])
        )
    )


def placeholder_fill(palette):
    """The fill of a picture still loading: the card, faintly shaded."""
    return blend(palette.color(_ROLE.Base), palette.color(_ROLE.Text), PLACEHOLDER_TINT)


def release_summary_html(html, accent, tag_fill, muted):
    """A release summary for its card: each item's scope as a small tag in
    the accent, "and N more" muted, the "New:" intro dropped (the card
    says it is a release)."""
    tag = (
        f'<li><span style="color: {accent}; background-color: {tag_fill};">'
        r"&nbsp;\1&nbsp;</span>&nbsp; "
    )
    html = _INTRO_LINE.sub("", html)
    html = _SCOPED_ITEM.sub(tag, html)

    return _MORE_LINE.sub(rf'<p style="color: {muted};">\1</p>', html)


def cropped(pixmap, width, height, ratio):
    """``pixmap`` scaled to fill ``width`` x ``height`` and centre-cropped,
    sharp at device pixel ``ratio``."""
    size = QtCore.QSize(round(width * ratio), round(height * ratio))
    scaled = pixmap.scaled(
        size,
        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    left = (scaled.width() - size.width()) // 2
    top = (scaled.height() - size.height()) // 2
    result = scaled.copy(left, top, size.width(), size.height())
    result.setDevicePixelRatio(ratio)

    return result


def fitted(pixmap, width, height, ratio):
    """``pixmap`` scaled to fit whole inside ``width`` x ``height``, its
    aspect kept, sharp at device pixel ``ratio``."""
    size = QtCore.QSize(round(width * ratio), round(height * ratio))
    result = pixmap.scaled(
        size,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    result.setDevicePixelRatio(ratio)

    return result


def clamp_rich_text(html, font, width, lines):
    """``html`` cut to what fits in ``lines`` lines of ``font`` at ``width``,
    measured with the real layout (paragraph spacing and list margins
    count). It ends on a whole line, with an ellipsis when cut; a cut inside
    a list item ends instead after the last whole block (the previous item,
    or the paragraph introducing the list). Returns ``(html, cut)``."""
    document = QtGui.QTextDocument()
    document.setDefaultFont(font)
    document.setDocumentMargin(0)
    document.setHtml(html)
    document.setTextWidth(max(width, 1))

    budget = QtGui.QFontMetricsF(font).lineSpacing() * lines

    if document.size().height() <= budget + 0.5:
        return html, False

    layout = document.documentLayout()
    end = None
    whole_block = True
    block = document.begin()

    while block.isValid():
        top = layout.blockBoundingRect(block).top()
        text_layout = block.layout()
        fitting = [
            text_layout.lineAt(index)
            for index in range(text_layout.lineCount())
            if top + text_layout.lineAt(index).rect().bottom() <= budget + 0.5
        ]

        # The whole block fits: a clean place to stop.
        if len(fitting) == text_layout.lineCount():
            end = block.position() + block.length() - 1
            block = block.next()

            continue

        # Part of a paragraph fits: stop after its last whole line. Part of
        # a list item does not: stop after the last whole block instead.
        if fitting and block.textList() is None:
            last = fitting[-1]
            end = block.position() + last.textStart() + last.textLength()
            whole_block = False

        break

    first = document.begin()

    if end is None:
        end = first.position() + first.layout().lineAt(0).textLength()
        whole_block = False

    # The ellipsis follows the last word, not the space after it.
    while not whole_block and end > 0 and document.characterAt(end - 1).isspace():
        end -= 1

    cursor = QtGui.QTextCursor(document)
    cursor.setPosition(end)
    cursor.movePosition(
        QtGui.QTextCursor.MoveOperation.End, QtGui.QTextCursor.MoveMode.KeepAnchor
    )
    cursor.removeSelectedText()
    cursor.insertText(" …" if whole_block else "…")

    # The ellipsis may not fit on the last line: give up words until it does.
    while document.size().height() > budget + 0.5 and cursor.position() > 2:
        cursor.movePosition(
            QtGui.QTextCursor.MoveOperation.PreviousWord,
            QtGui.QTextCursor.MoveMode.KeepAnchor,
            2,
        )
        cursor.removeSelectedText()

        while (
            cursor.position() > 0
            and document.characterAt(cursor.position() - 1).isspace()
        ):
            cursor.deletePreviousChar()

        cursor.insertText("…")

    return document.toHtml(), True


def picture_pair_cells(width, caption_height):
    """Where a lead card's two pictures go in a ``width`` wide area, each
    with ``caption_height`` beneath: ``(x, y, w, h)`` per picture, and the
    area's height. Side by side, the two are equal halves either side of a
    GRID gap; narrower than PAIR_MIN_WIDTH they stack, each full width. Every
    picture is PAIR_ASPECT."""

    if width < PAIR_MIN_WIDTH:
        height = round(width / PAIR_ASPECT)
        step = height + caption_height + GRID
        cells = [(0, index * step, width, height) for index in (0, 1)]

    else:
        side = (width - GRID) // 2
        height = round(side / PAIR_ASPECT)
        cells = [(index * (side + GRID), 0, side, height) for index in (0, 1)]

    _x, y, _w, h = cells[-1]

    return cells, y + h + caption_height


def _rounded(rect, radius=CORNER_RADIUS):
    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(rect), radius, radius)

    return path


class _ElidedLabel(QtWidgets.QWidget):
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


class _CardFrame(QtWidgets.QFrame):
    """A rounded card with a hover state and an optional banner on top,
    painted from its palette."""

    clicked = QtCore.Signal()
    resized = QtCore.Signal()
    palette_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover)
        self._hovered = False

        # Never taller than its contents: a layout's spare room goes elsewhere.
        policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
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
        painter.setClipPath(_rounded(body))

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


class _Thumbnail(QtWidgets.QWidget):
    """A small rounded muted shape; the picture, once loaded, centred on it
    whole, so a picture of another shape is letterboxed, never cropped."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.pixmap = None
        self.setFixedSize(*THUMBNAIL_SIZE)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setClipPath(_rounded(self.rect(), CORNER_RADIUS - 2))
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


class _PicturePair(QtWidgets.QWidget):
    """Two captioned pictures, side by side at equal height, or stacked when
    narrow; each centre-cropped to PAIR_ASPECT. A click on one emits
    ``picture_clicked`` with its index, and goes no further."""

    picture_clicked = QtCore.Signal(int)

    def __init__(self, captions, alts, parent=None):
        super().__init__(parent)

        self.captions = captions
        self.alts = alts

        #: The loaded pictures, as loaded: every crop is made from these.
        self.pixmaps = [None] * len(captions)

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
        self.pixmaps[index] = pixmap
        self._crops.pop(index, None)
        self.update()

    def _caption_height(self):
        """Room for a caption line beneath each picture; none without any."""

        if not any(self.captions):
            return 0

        return QtGui.QFontMetrics(self.font()).height() + GRID // 2

    def _rects(self, width):
        """Where each picture goes at ``width``."""
        cells, _height = picture_pair_cells(width, self._caption_height())

        return [QtCore.QRect(*cell) for cell in cells]

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return picture_pair_cells(width, self._caption_height())[1]

    def sizeHint(self):
        width = self.width() if self.width() > 0 else PAIR_MIN_WIDTH

        return QtCore.QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self):
        return QtCore.QSize(0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self._crops = {}

    def _crop(self, index, rect):
        """Picture ``index`` cover-cropped to ``rect``, made once per size
        from the loaded picture, sharp at the device pixel ratio."""
        crop = self._crops.get(index)

        if crop is None:
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
            painter.setClipPath(_rounded(rect, CORNER_RADIUS - 2))

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


class FeedPostCard(HasTraits):
    """One post's card, lead or compact; a lead card with two pictures shows
    them side by side."""

    #: The post shown.
    post = Instance(FeedPost)

    #: The SciBotsFeedController its clicks go to; None ignores them.
    controller = Any()

    #: Whether it is its group's lead card.
    lead = Bool(False)

    #: The group's accent, a colour name.
    accent = Str()

    #: Fonts by part ("title", "small", "body", "link") from a host with its own
    #: type roles; a part not given is the card's font resized.
    fonts = Dict(Str, Any)

    #: The card.
    control = Any()

    #: The summary label and the "Show more" note.
    _summary = Any()
    _more = Any()

    #: ``(label, html)`` of the labels holding links.
    _link_labels = List()

    #: The whole summary as rich text, links styled; the collapsed card
    #: shows it cut to whole lines.
    _summary_html = Str()

    #: The compact row's picture.
    _thumbnail = Any()

    #: A compact release row's first feature, shown while collapsed.
    _teaser = Any()

    #: The loaded picture.
    _picture = Any()

    #: A lead card's two pictures, and their loaded pixmaps.
    _pair = Any()
    _pair_pixmaps = Dict(Int, Any)

    def create(self, parent):
        """Build the card."""
        post = self.post
        self.control = card = _CardFrame(parent)
        card.resized.connect(self._on_resized)

        if self._has_summary():
            card.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(self._toggle)

        elif self._is_link_row():
            card.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(lambda: self._open_link(READ_MORE_HREF))

        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(2 * GRID, 2 * GRID, 2 * GRID, GRID + GRID // 2)
        layout.setSpacing(GRID)

        pair = self.lead and len(post.images) == 2

        if pair:
            layout.addWidget(self._create_pair())

        if self.lead:
            layout.addWidget(self._create_meta())
            layout.addWidget(self._create_title(LEAD_TITLE_LINES, LEAD_TITLE_POINTS))

        else:
            layout.addLayout(self._create_compact_head())

        self._summary = self._create_summary()
        layout.addWidget(self._summary)
        layout.addLayout(self._create_footer())

        self._render_links()

        if pair:
            for index, (src, _caption, _alt) in enumerate(post.images):
                thumbnail_loader().request(src, partial(self._show_pair_picture, index))

        elif post.image:
            self._show_loading()
            thumbnail_loader().request(post.image, self._show_picture)

        self._show_expanded()

        return card

    def dispose(self):
        """Let go of the post and the widgets; the caller deletes the card."""
        self.trait_set(
            post=None,
            controller=None,
            _summary=None,
            _more=None,
            _link_labels=[],
            _thumbnail=None,
            _teaser=None,
            _pair=None,
            _pair_pixmaps={},
        )

    # ------------------------------------------------------------------ #
    # Building                                                            #
    # ------------------------------------------------------------------ #

    def _has_summary(self):
        return bool(self.post.summary or self.post.summary_html)

    def _is_link_row(self):
        """Whether it is a compact row with nothing to expand, so the row
        itself opens the post instead of a "Read more" line."""
        return not self.lead and not self._has_summary()

    def _create_meta(self):
        """ "NEWSLETTER · Sci-Bots · September 2026": the kind in the accent,
        the rest muted."""
        post = self.post
        parts = [post.source_label, format_post_date(post)]
        separator = "&nbsp;&nbsp;·&nbsp;&nbsp;"
        rest = separator.join(escape(part) for part in parts if part)
        muted = self.control.palette().color(_ROLE.PlaceholderText).name()
        kind = KIND_LABELS[post.kind].upper()

        label = QtWidgets.QLabel(self.control)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setFont(self._font("small", SMALL_POINTS))
        label.setText(
            f'<span style="color: {self.accent}; font-weight: 700;">{kind}</span>'
            f'<span style="color: {muted};">{separator}{rest}</span>'
        )

        return label

    def _create_title(self, lines, points):
        title = _ElidedLabel(self.post.title, lines, self.control)
        title.setFont(self._font("title", points, bold=True))

        return title

    def _create_compact_head(self):
        """Meta over title (over a release's first feature) at the left, the
        picture at the right."""
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(GRID + GRID // 2)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(GRID // 2)

        text.addWidget(self._create_meta())
        text.addWidget(self._create_title(COMPACT_TITLE_LINES, COMPACT_TITLE_POINTS))

        teaser = summary_teaser(self.post)

        if self.post.kind == "release" and teaser:
            self._teaser = _ElidedLabel(teaser, 1, self.control)
            self._teaser.setForegroundRole(_ROLE.PlaceholderText)
            text.addWidget(self._teaser)

        text.addStretch()
        head.addLayout(text, 1)

        if self.post.image:
            self._thumbnail = _Thumbnail(self.control)
            head.addWidget(self._thumbnail, 0, _ALIGN.AlignTop)

        return head

    def _create_summary(self):
        """The rich summary if there is one, else the plain one."""
        post = self.post
        summary = QtWidgets.QLabel(self.control)
        summary.setFont(self._font("body", 0))
        summary.setWordWrap(True)
        summary.setAlignment(_ALIGN.AlignLeft | _ALIGN.AlignTop)

        # Plain text too goes through rich text: the collapsed summary is
        # cut by the rich text layout.
        summary.setTextFormat(QtCore.Qt.TextFormat.RichText)

        if post.summary_html:
            html = post.summary_html
            palette = self.control.palette()

            if post.kind == "release":
                accent = QtGui.QColor(self.accent)
                tag_fill = blend(palette.color(_ROLE.Base), accent, TAG_TINT)
                html = release_summary_html(
                    html,
                    self.accent,
                    tag_fill.name(),
                    palette.color(_ROLE.PlaceholderText).name(),
                )

            summary.setOpenExternalLinks(False)
            summary.setToolTip(post.summary)
            summary.linkActivated.connect(self._open_link)
            self._link_labels.append((summary, html))

        else:
            self._link_labels.append(
                (summary, f"<p>{escape(post.summary).replace(chr(10), '<br>')}</p>")
            )

        summary.setVisible(bool(post.summary or post.summary_html))

        return summary

    def _create_footer(self):
        """ "Show more" at the left; Remove (pushed) and Read more (but on a
        link row) at the right, in the accent."""
        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(2 * GRID)

        self._more = QtWidgets.QLabel(self.control)
        self._more.setForegroundRole(_ROLE.PlaceholderText)
        self._more.setFont(self._font("small", SMALL_POINTS))
        footer.addWidget(self._more)
        footer.addStretch()

        links = [] if self._is_link_row() else [("Read more ›", READ_MORE_HREF)]

        if self.post.origin == ORIGIN_PUSHED:
            links.insert(0, ("Remove", REMOVE_HREF))

        for text, href in links:
            label = QtWidgets.QLabel(self.control)
            label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            label.setOpenExternalLinks(False)
            label.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            label.setFont(self._font("link", 0))
            label.linkActivated.connect(self._open_link)
            text = f"<b>{text}</b>" if href == READ_MORE_HREF else text
            self._link_labels.append((label, f'<a href="{href}">{text}</a>'))
            footer.addWidget(label)

        return footer

    # ------------------------------------------------------------------ #
    # Reactions                                                           #
    # ------------------------------------------------------------------ #

    def _render_links(self):
        """Links in the accent, not underlined: Qt's HTML import would take
        the application's link colour, which a preview does not use."""
        style = f"color: {self.accent}; text-decoration: none;"

        for label, html in self._link_labels:
            styled = html.replace("<a ", f'<a style="{style}" ')

            if label is self._summary:
                self._summary_html = styled

            label.setText(styled)

        self._show_expanded()

    def _open_link(self, href):
        if self.controller is None or self.post is None:
            return

        if href == READ_MORE_HREF:
            self.controller.open_post(self.post)

        elif href == REMOVE_HREF:
            self.controller.remove(self.post.id)

        else:
            self.controller.open_link(href)

    def _font(self, part, points, bold=False):
        """The host's font for ``part``, or the card's resized by
        ``points``."""
        font = self.fonts.get(part)

        if font is None:
            return scaled_font(self.control, points, bold)

        return QtGui.QFont(font)

    def _create_pair(self):
        images = self.post.images
        self._pair = _PicturePair(
            [caption for _src, caption, _alt in images],
            [alt for _src, _caption, alt in images],
            self.control,
        )
        self._pair.setFont(self._font("small", SMALL_POINTS))
        self._pair.picture_clicked.connect(self._preview_picture)

        return self._pair

    def _show_pair_picture(self, index, pixmap):

        if self._pair is not None and pixmap is not None:
            self._pair_pixmaps[index] = pixmap
            self._pair.set_picture(index, pixmap)

    def _preview_picture(self, index):
        """The picture larger; the post's link while it is still loading."""
        pixmap = self._pair_pixmaps.get(index)

        if pixmap is None:
            self._open_link(READ_MORE_HREF)

            return

        show_picture_preview(pixmap, self.post.images[index][1], self.control.window())

    def _toggle(self):
        if self.controller is not None and self.post is not None:
            self.controller.toggle_expanded(self.post)

    def _on_resized(self):
        self._show_expanded()
        self._show_banner()

    @observe("post:expanded", post_init=True)
    def _show_expanded(self, event=None):
        """A lead card shows its summary's first lines, a compact row none,
        until expanded."""

        if self._summary is None or self.post is None:
            return

        summary = self._summary
        has_summary = self._has_summary()
        lines = 0

        if self.lead:
            release = self.post.kind == "release"
            lines = RELEASE_COLLAPSED_LINES if release else SUMMARY_COLLAPSED_LINES

        full = self._summary_html
        collapsed, overflows = full, True

        if lines:
            collapsed, overflows = clamp_rich_text(
                full, summary.font(), summary.width(), lines
            )

        text = full if self.post.expanded else collapsed

        if summary.text() != text:
            summary.setText(text)

        summary.setVisible(has_summary and (self.post.expanded or lines > 0))
        self._more.setVisible(has_summary and overflows)
        self._more.setText("Show less" if self.post.expanded else "Show more")

        if self._teaser is not None:
            self._teaser.setVisible(not self.post.expanded)

    def _show_loading(self):
        if self.lead:
            self._set_banner("loading", BANNER_LOADING_HEIGHT)

    def _show_picture(self, pixmap):
        """Show the loaded picture; None removes its placeholder."""

        if self.post is None:
            return

        if pixmap is None:
            if self.lead:
                self._set_banner(None, 0)

            elif self._thumbnail is not None:
                self._thumbnail.hide()

            return

        self._picture = pixmap

        if self.lead:
            self._show_banner()

        elif self._thumbnail is not None:
            ratio = self.control.devicePixelRatioF()
            self._thumbnail.pixmap = fitted(pixmap, *THUMBNAIL_SIZE, ratio)
            self._thumbnail.update()

    def _show_banner(self):
        """The picture across the card's top, at most BANNER_MAX_HEIGHT."""

        if not self.lead or self.control is None or self._picture is None:
            return

        width = self.control.width()
        aspect = self._picture.width() / max(self._picture.height(), 1)
        height = min(round(width / aspect), BANNER_MAX_HEIGHT)
        ratio = self.control.devicePixelRatioF()

        self._set_banner(cropped(self._picture, width, height, ratio), height)

    def _set_banner(self, banner, height):
        card = self.control
        card.banner = banner
        card.banner_height = height
        margins = card.layout().contentsMargins()
        margins.setTop(height + 2 * GRID)
        card.layout().setContentsMargins(margins)
        card.update()

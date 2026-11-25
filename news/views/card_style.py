# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""A feed post card's measures and look: the 8-pixel grid, picture and
line limits, colours from the palette, and picture fitting."""

# Standard library imports.
import math
import re

# Enthought library imports.
from pyface.qt import QtCore, QtGui

#: The grid all spacing is a multiple of.
GRID = 8

#: Corner radius of cards, pictures and banners.
CORNER_RADIUS = 10

#: A lead card's picture always fills the card's width, edge to edge, at
#: its own aspect up to this share of the width tall and this many pixels;
#: past that it is cropped top and bottom, centred, never padded. A wide
#: banner (about 2.7:1) is never cropped; a square photo shows its middle.
#: This tall while it loads.
PICTURE_MAX_SHARE = 0.62
PICTURE_CEILING = 400
BANNER_LOADING_HEIGHT = 112

#: A compact row's picture box; the picture fits inside it whole.
THUMBNAIL_SIZE = (11 * GRID, 7 * GRID)

#: A lead card's two pictures: side by side unless the card is narrower
#: than PAIR_MIN_WIDTH, then stacked. Side by side they share one aspect
#: (width over height), the less extreme of theirs, kept within
#: PAIR_ASPECT_RANGE; PAIR_ASPECT until they have loaded.
PAIR_ASPECT = 4 / 3
PAIR_ASPECT_RANGE = (3 / 4, 2.0)
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


def picture_cap(width):
    """The most height (px) a lead card's picture takes at ``width``."""
    return min(PICTURE_MAX_SHARE * width, PICTURE_CEILING)


def full_width_picture_height(width, picture_width, picture_height):
    """The height (px) of a picture filling a ``width`` wide card: its own
    aspect's, capped by ``picture_cap`` (it is then cover-cropped)."""
    aspect = max(picture_width, 1) / max(picture_height, 1)

    return round(min(width / aspect, picture_cap(width)))


def pair_aspect(aspects):
    """The one aspect two pictures share side by side: the less extreme of
    theirs (the nearer to square), within PAIR_ASPECT_RANGE."""
    aspect = min(aspects, key=lambda value: abs(math.log(max(value, 1e-6))))
    low, high = PAIR_ASPECT_RANGE

    return min(max(aspect, low), high)


def picture_pair_cells(width, caption_height, aspects=(PAIR_ASPECT, PAIR_ASPECT)):
    """Where a lead card's two pictures go in a ``width`` wide area, each
    with ``caption_height`` beneath: ``(x, y, w, h)`` per picture, and the
    area's height. Side by side (PAIR_MIN_WIDTH or wider) they are equal
    halves either side of a GRID gap at their shared ``pair_aspect``;
    narrower they stack, each full width at its own aspect, as tall as
    ``picture_cap`` allows (``full_width_picture_height``). ``aspects``
    are the pictures' width over height."""

    if width < PAIR_MIN_WIDTH:
        cells = []
        top = 0

        for aspect in aspects:
            height = full_width_picture_height(width, aspect, 1)
            cells.append((0, top, width, height))
            top += height + caption_height + GRID

        return cells, top - GRID

    side = (width - GRID) // 2
    height = round(side / pair_aspect(aspects))
    cells = [(index * (side + GRID), 0, side, height) for index in (0, 1)]

    return cells, height + caption_height


def rounded_rect_path(rect, radius=CORNER_RADIUS):
    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(rect), radius, radius)

    return path
